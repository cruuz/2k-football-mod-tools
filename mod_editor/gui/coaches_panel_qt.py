"""★ Rosters > Coaches: who coaches each club in your build, and the staff changes you want.

The page reads the head coach of every club out of the roster you opened (a game disc), pairs each club with its 2026
defensive coordinator from the Studio's own data, and lets you change the staff the way a team owner would: swap two
clubs' head coaches, hire a different head coach (the coach he replaces goes to his old club, or is let go when you hire a
brand new person), create a coach, change a coordinator, and decide whether a coach who arrives brings his old playbook.

Nothing here writes a disc or a save.  The changes are one small document, the ``staff`` section of the roster edits
(``mod_editor/core/nfl2k5_staff_ui.py`` has its shape and every rule), which Build applies when it makes your disc.
Every change is announced by ``edit_made(label, before, after)``; ★ Rosters records it on its own Undo stack so the
toolbar's Undo and Redo work on staff changes like on any other roster edit.  A franchise save is edited on the
Franchise page instead (Coaches > Swap, Fire and hire).

EXPERIMENTAL / UNWITNESSED: the game has not been played with a moved coach yet.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from PyQt5.QtCore import QRect, QSize, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QBrush, QColor, QFont, QImage, QPainter, QPixmap
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
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
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mod_editor.core import nfl2k5_staff_ui as ui
from mod_editor.gui.ux_text import WrappedLabel, plain_error

STAFF_FILTER = "Staff files (*.json);;All files (*)"
HEADERS = ("Club", "Head coach", "Defensive coordinator", "Change")
CHANGED_BRUSH = QColor(240, 180, 41, 60)
SOURCE_NOTE = {
    "none": "Open a game disc (top right of the Studio, or Open disc roster on the Roster tab) to plan staff changes.",
    "empty": "This roster has no head coach records, so there is no staff to plan.",
    "save": ("This roster came from an Xbox save. Plan staff changes for a build on a game disc. "
             "To change the coaches inside a franchise save, use the Franchise tab, Coaches."),
}
PLAYBOOK_TIP = ("Off: the club keeps its own playbook and only the coach's play calling style arrives. On: the club's "
                "playbook becomes a copy of the playbook of the club he came from (a new coach borrows the playbook of the "
                "coach he plays like).")
FACE_SIZE = QSize(96, 72)
_FACES: dict[tuple[str, int, int], QPixmap] = {}


def monogram(name: str, size: QSize = FACE_SIZE) -> QPixmap:
    """A plain initials tile for a coach with no painted face (a new coach, or a retail coach)."""

    pixmap = QPixmap(size)
    pixmap.fill(QColor("#1a2940"))
    letters = "".join(part[0] for part in name.replace("-", " ").split()[:2]).upper() or "?"
    painter = QPainter(pixmap)
    painter.setPen(QColor("#9fb2cd"))
    font = QFont()
    font.setBold(True)
    font.setPixelSize(max(12, size.height() // 2))
    painter.setFont(font)
    painter.drawText(QRect(0, 0, size.width(), size.height()), Qt.AlignCenter, letters)
    painter.end()
    return pixmap


def face_pixmap(code: str | None, name: str, size: QSize = FACE_SIZE) -> QPixmap:
    """A 2026 head coach's painted face from the Studio's coach art, else his initials."""

    path = ui.face_path(code) if code else None
    if path is None:
        return monogram(name, size)
    key = (code or "", size.width(), size.height())
    if key not in _FACES:
        image = QImage(str(path))
        if image.isNull():
            return monogram(name, size)
        face = image.copy(0, 0, min(128, image.width()), min(96, image.height()))
        _FACES[key] = QPixmap.fromImage(face).scaled(size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    return _FACES[key]


# --------------------------------------------------------------------------------------------- dialogs
class PickDialog(QDialog):
    """Choose one row from a filtered list; a sentence says what the choice will do."""

    def __init__(self, title: str, intro: str, rows: Sequence[tuple[Any, str]], describe: Callable[[Any], str],
                 parent: QWidget | None = None, *, accessible: str = "Choices") -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self._describe = describe
        self._rows = list(rows)
        layout = QVBoxLayout(self)
        hint = QLabel(intro)
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Type to narrow the list")
        self.filter.setAccessibleName(f"Filter {accessible}")
        self.filter.textChanged.connect(self._fill)
        layout.addWidget(self.filter)
        self.list = QListWidget()
        self.list.setAccessibleName(accessible)
        self.list.currentRowChanged.connect(self._row_changed)
        self.list.itemDoubleClicked.connect(lambda _item: self.accept())
        layout.addWidget(self.list, 1)
        self.summary = WrappedLabel("Choose one from the list.")
        self.summary.setAccessibleName("What will happen")
        layout.addWidget(self.summary)
        self.extra = QHBoxLayout()
        layout.addLayout(self.extra)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.ok_button = buttons.button(QDialogButtonBox.Ok)
        self.ok_button.setEnabled(False)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._fill()
        self.resize(500, 560)

    def _fill(self, *_args: object) -> None:
        needle = self.filter.text().strip().casefold()
        self.list.blockSignals(True)
        self.list.clear()
        for key, text in self._rows:
            if needle and needle not in text.casefold():
                continue
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, key)
            self.list.addItem(item)
        self.list.blockSignals(False)
        self._row_changed(-1)

    def _row_changed(self, _row: int) -> None:
        key = self.chosen()
        self.ok_button.setEnabled(key is not None)
        self.summary.setText(self._describe(key) if key is not None else "Choose one from the list.")

    def chosen(self) -> Any:
        item = self.list.currentItem()
        return None if item is None else item.data(Qt.UserRole)

    def choose(self, key: Any) -> bool:
        for row in range(self.list.count()):
            if self.list.item(row).data(Qt.UserRole) == key:
                self.list.setCurrentRow(row)
                return True
        return False


class NewCoachDialog(QDialog):
    """Create a coach: name, biography, the game's sideline model, whose play calling he borrows and his overall rating."""

    def __init__(self, club_label: str, bodies: Mapping[int, str], styles: Sequence[tuple[str, str]],
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"New head coach: {club_label}")
        layout = QVBoxLayout(self)
        intro = WrappedLabel(f"A brand new person takes over {club_label}. The coach he replaces is let go and leaves "
                             "the roster unless you hire him back somewhere.")
        layout.addWidget(intro)
        names = QHBoxLayout()
        self.first_field = QLineEdit()
        self.first_field.setPlaceholderText("First name")
        self.first_field.setAccessibleName("New coach first name")
        self.first_field.setMaxLength(ui.NAME_LIMIT)
        self.last_field = QLineEdit()
        self.last_field.setPlaceholderText("Last name")
        self.last_field.setAccessibleName("New coach last name")
        self.last_field.setMaxLength(ui.NAME_LIMIT)
        names.addWidget(self.first_field)
        names.addWidget(self.last_field)
        layout.addLayout(names)
        self.bio_fields: list[QLineEdit] = []
        for number in range(1, 4):
            field = QLineEdit()
            field.setPlaceholderText(f"Biography line {number} (optional)")
            field.setAccessibleName(f"New coach biography line {number}")
            field.setMaxLength(ui.BIO_LIMIT)
            self.bio_fields.append(field)
            layout.addWidget(field)
        row = QHBoxLayout()
        row.addWidget(QLabel("Looks like"))
        self.body_combo = QComboBox()
        self.body_combo.setAccessibleName("Sideline model")
        self.body_combo.setToolTip("The game's sideline coach models. His look is the model; colours and face come from the "
                                   "coach art of the build.")
        for body in ui.COACH_BODIES:
            self.body_combo.addItem(bodies.get(body, f"Model c{body:02d}"), body)
        self.body_combo.setCurrentIndex(max(0, self.body_combo.findData(ui.DEFAULT_BODY)))
        row.addWidget(self.body_combo, 1)
        layout.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(QLabel("Calls plays like"))
        self.style_combo = QComboBox()
        self.style_combo.setAccessibleName("Play calling style")
        self.style_combo.setToolTip("He copies this coach's play-calling tendencies. Without one he plays like the game's own "
                                    "created coach.")
        self.style_combo.addItem("The game's own created coach", None)
        for code, text in styles:
            self.style_combo.addItem(text, code)
        row.addWidget(self.style_combo, 1)
        layout.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(QLabel("Overall rating"))
        self.overall_spin = QSpinBox()
        self.overall_spin.setRange(0, 99)
        self.overall_spin.setValue(70)
        self.overall_spin.setAccessibleName("Overall rating")
        row.addWidget(self.overall_spin)
        row.addStretch(1)
        layout.addLayout(row)
        self.problem = WrappedLabel("")
        self.problem.setAccessibleName("What to fix")
        layout.addWidget(self.problem)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.ok_button = buttons.button(QDialogButtonBox.Ok)
        self.ok_button.setEnabled(False)
        buttons.accepted.connect(self._try_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        for field in (self.first_field, self.last_field, *self.bio_fields):
            field.textChanged.connect(self._names_changed)
        self.resize(460, 440)

    def _names_changed(self, *_args: object) -> None:
        self.ok_button.setEnabled(bool(self.first_field.text().strip()) and bool(self.last_field.text().strip()))
        self.problem.setText("")

    def spec(self) -> dict[str, Any]:
        """The new coach in the document's shape; raises StaffUiError in plain words when something is wrong."""

        return ui.new_coach_spec(self.first_field.text(), self.last_field.text(), bio=[f.text() for f in self.bio_fields],
                                 body=int(self.body_combo.currentData()), style=self.style_combo.currentData(),
                                 overall=self.overall_spin.value())

    def _try_accept(self) -> None:
        try:
            self.spec()
        except ui.StaffUiError as exc:
            self.problem.setText(str(exc))
            return
        self.accept()


# --------------------------------------------------------------------------------------------- the page
class CoachesPanel(QWidget):
    """The Coaches page of ★ Rosters."""

    edit_made = pyqtSignal(str, object, object)        # label, staff document before, staff document after
    staff_replaced = pyqtSignal()                      # the whole plan changed without a user edit (new roster, undo, file)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._rows: list[ui.HeadCoachRow] = []
        self._staff: dict[str, Any] = ui.empty()
        self._state = "none"                           # none | save | disc
        self._quiet = False
        self.body_provider: Callable[[], bytes] | None = None
        self._engine = ui.EnginePlan()
        self._engine_pending = False
        self._engine_timer = QTimer(self)
        self._engine_timer.setSingleShot(True)
        self._engine_timer.setInterval(300)
        self._engine_timer.timeout.connect(self._engine_due)
        self._build()
        self._refresh()

    # ------------------------------------------------------------------ construction
    def _build(self) -> None:
        layout = QVBoxLayout(self)
        intro = WrappedLabel(
            "Choose who coaches each club in your build. Swap two clubs' head coaches, hire a different head coach, "
            "create a new one, or change a defensive coordinator. A coach keeps his career, ratings and play calling "
            "when he moves. Nothing changes until you export roster edits and build: this page never touches your disc. "
            "Undo and Redo above work on staff changes too.")
        layout.addWidget(intro)
        self.state_label = WrappedLabel("")
        self.state_label.setObjectName("coachesState")
        self.state_label.setAccessibleName("Staff page state")
        layout.addWidget(self.state_label)

        splitter = QSplitter(Qt.Horizontal)
        left = QWidget()
        left_box = QVBoxLayout(left)
        left_box.setContentsMargins(0, 0, 0, 0)
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Find a club, coach or coordinator")
        self.filter.setAccessibleName("Find a club, coach or coordinator")
        self.filter.textChanged.connect(self._apply_filter)
        left_box.addWidget(self.filter)
        self.table = QTableWidget(0, len(HEADERS))
        self.table.setHorizontalHeaderLabels(list(HEADERS))
        self.table.setAccessibleName("Clubs and their coaches")
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.currentCellChanged.connect(lambda row, _c, _pr, _pc: self._show_club())
        left_box.addWidget(self.table, 1)
        splitter.addWidget(left)

        right = QWidget()
        right_box = QVBoxLayout(right)
        right_box.setContentsMargins(0, 0, 0, 0)
        self.club_title = QLabel("")
        title_font = self.club_title.font()
        title_font.setPointSizeF(title_font.pointSizeF() + 3)
        title_font.setBold(True)
        self.club_title.setFont(title_font)
        right_box.addWidget(self.club_title)
        head = QGroupBox("Head coach")
        head_row = QHBoxLayout(head)
        self.face = QLabel()
        self.face.setFixedSize(FACE_SIZE)
        self.face.setAccessibleName("Head coach picture")
        self.face.setScaledContents(False)
        head_row.addWidget(self.face, 0, Qt.AlignTop)
        text = QVBoxLayout()
        self.coach_name = QLabel("")
        name_font = self.coach_name.font()
        name_font.setBold(True)
        name_font.setPointSizeF(name_font.pointSizeF() + 1)
        self.coach_name.setFont(name_font)
        self.coach_origin = WrappedLabel("")
        self.coach_career = WrappedLabel("")
        self.coach_style = WrappedLabel("")
        self.coach_ratings = WrappedLabel("")
        self.coach_engine = WrappedLabel("")
        self.coach_engine.setAccessibleName("What the build will do for this club")
        for label in (self.coach_name, self.coach_origin, self.coach_career, self.coach_style, self.coach_ratings,
                      self.coach_engine):
            text.addWidget(label)
        text.addStretch(1)
        head_row.addLayout(text, 1)
        right_box.addWidget(head)
        self.playbook_check = QCheckBox("He brings his old club's playbook")
        self.playbook_check.setToolTip(PLAYBOOK_TIP)
        self.playbook_check.toggled.connect(self._playbook_toggled)
        right_box.addWidget(self.playbook_check)
        defense = QGroupBox("Defensive coordinator")
        defense_box = QVBoxLayout(defense)
        self.dc_name = QLabel("")
        dc_font = self.dc_name.font()
        dc_font.setBold(True)
        self.dc_name.setFont(dc_font)
        self.dc_detail = WrappedLabel("")
        defense_box.addWidget(self.dc_name)
        defense_box.addWidget(self.dc_detail)
        right_box.addWidget(defense)

        actions = QHBoxLayout()
        self.swap_button = QPushButton("Swap head coaches…")
        self.swap_button.setToolTip("Exchange this club's head coach with another club's. Nobody loses a job.")
        self.swap_button.clicked.connect(self._swap_clicked)
        self.hire_button = QPushButton("Hire a head coach…")
        self.hire_button.setToolTip("Pick the coach who takes this job: a head coach from another club (the two clubs swap), "
                                    "or a brand new person you create.")
        self.hire_button.clicked.connect(self._hire_clicked)
        self.dc_button = QPushButton("Change coordinator…")
        self.dc_button.setToolTip("Give this club another club's defensive coordinator. The two defenses swap.")
        self.dc_button.clicked.connect(self._dc_clicked)
        for button in (self.swap_button, self.hire_button, self.dc_button):
            actions.addWidget(button)
        actions.addStretch(1)
        right_box.addLayout(actions)
        right_box.addStretch(1)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([620, 400])
        splitter.setChildrenCollapsible(False)
        layout.addWidget(splitter, 1)

        changes = QGroupBox("Staff changes")
        changes_box = QVBoxLayout(changes)
        self.changes_text = QPlainTextEdit()
        self.changes_text.setReadOnly(True)
        self.changes_text.setMaximumHeight(110)
        self.changes_text.setAccessibleName("Staff changes in words")
        changes_box.addWidget(self.changes_text)
        self.notes_text = WrappedLabel("")
        self.notes_text.setAccessibleName("Notes from the build")
        changes_box.addWidget(self.notes_text)
        row = QHBoxLayout()
        self.reset_button = QPushButton("Put every coach back")
        self.reset_button.setToolTip("Clear every staff change and go back to the staff on the roster you opened.")
        self.reset_button.clicked.connect(self.reset_all)
        self.save_button = QPushButton("Save staff file…")
        self.save_button.setToolTip("Save these staff changes as a small file you can load again or share.")
        self.save_button.clicked.connect(self._save_file)
        self.load_button = QPushButton("Load staff file…")
        self.load_button.setToolTip("Replace the staff changes with the ones in a staff file. It is checked against this roster first.")
        self.load_button.clicked.connect(self._load_file)
        for button in (self.reset_button, self.save_button, self.load_button):
            row.addWidget(button)
        row.addStretch(1)
        self.count_label = QLabel("")
        row.addWidget(self.count_label)
        changes_box.addLayout(row)
        layout.addWidget(changes)

    # ------------------------------------------------------------------ the roster and the plan
    def set_roster(self, document: Any | None, *, kind: str = "disc") -> None:
        """Adopt the loaded roster (a disc) or say why there is nothing to plan; the plan starts empty."""

        self._staff = ui.empty()
        if document is None:
            self._rows, self._state = [], "none"
        elif kind != "disc":
            self._rows, self._state = [], "save"
        else:
            self._rows, self._state = ui.read_head_coaches(document), "disc"
            if not any(row.name for row in self._rows):
                self._rows, self._state = [], "empty"
        self._refresh(select=0 if self._rows else None)
        self.staff_replaced.emit()

    @property
    def state(self) -> str:
        """``disc`` when there is a roster to plan on, else why not: ``none``, ``save`` or ``empty``."""

        return self._state

    def set_rows(self, rows: Sequence[ui.HeadCoachRow]) -> None:
        """Adopt head coaches read elsewhere (the tests and the screenshot tool use this)."""

        self._staff = ui.empty()
        self._rows, self._state = list(rows), "disc"
        self._refresh(select=0 if self._rows else None)
        self.staff_replaced.emit()

    @property
    def rows(self) -> list[ui.HeadCoachRow]:
        return list(self._rows)

    def staff(self) -> dict[str, Any]:
        return dict(self._staff)

    def has_changes(self) -> bool:
        return not ui.is_empty(self._staff)

    def change_count(self) -> int:
        """How many lines the plan has in words (a swap of two clubs is two)."""

        return len(ui.describe(self._rows, self._staff)) if self._state == "disc" else 0

    def set_staff(self, staff: Mapping[str, Any] | None) -> None:
        """Replace the whole plan without announcing an edit (undo, redo and a loaded file come through here)."""

        self._staff = dict(staff) if staff and not ui.is_empty(staff) else ui.empty()
        self._refresh()
        self.staff_replaced.emit()

    def export_staff(self) -> dict[str, Any]:
        """The staff section for the roster edits: empty when nothing changed, checked, in the engine's own form."""

        if not self.has_changes():
            return {}
        found = ui.problems(self._rows, self._staff)
        if found:
            raise ui.StaffUiError("The staff changes cannot be built: " + "; ".join(found))
        return ui.engine_normalized(self._staff)

    def _commit(self, label: str, staff: dict[str, Any]) -> bool:
        before = self._staff
        if staff == before:
            self._set_state_text("Nothing to change.")
            return False
        self._staff = staff
        self._refresh()
        self.edit_made.emit(label, before, staff)
        return True

    def _try(self, label: str, make: Callable[[], dict[str, Any]]) -> bool:
        if self._state != "disc":
            return False
        try:
            staff = make()
        except ui.StaffUiError as exc:
            self._set_state_text(f"Refused: {exc}")
            return False
        return self._commit(label, staff)

    # ------------------------------------------------------------------ public edits (the buttons call these)
    def swap_clubs(self, club_a: Any, club_b: Any) -> bool:
        if self._state != "disc":
            return False
        a, b = ui.club(club_a), ui.club(club_b)
        seats = ui.head_seats(self._rows, self._staff)
        names = [ui.occupant_name(seats[c.book], self._staff) for c in (a, b)]
        return self._try(f"{a.code} and {b.code} swap head coaches: {names[0]} goes to {b.code}, {names[1]} goes to {a.code}",
                         lambda: ui.swap_head_coaches(self._rows, self._staff, a, b))

    def move_coach(self, coach_name: str, to_club: Any) -> bool:
        target = ui.club(to_club)
        return self._try(f"{coach_name} takes the {target.code} head coach job",
                         lambda: ui.move_head_coach(self._rows, self._staff, coach_name, target))

    def hire_new_coach(self, club_: Any, spec: Mapping[str, Any]) -> bool:
        target = ui.club(club_)
        label = f"{target.code}: {spec.get('first', '')} {spec.get('last', '')} hired as a new head coach".replace("  ", " ")
        if self._state != "disc":
            return False
        try:
            staff, _new_id = ui.hire_created_coach(self._rows, self._staff, target, spec)
        except ui.StaffUiError as exc:
            self._set_state_text(f"Refused: {exc}")
            return False
        return self._commit(label, staff)

    def set_defense(self, club_: Any, dc_home: Any) -> bool:
        target, home = ui.club(club_), ui.club(dc_home)
        people = ui.coordinators()
        name = people[home.book].name if home.book in people else home.code
        return self._try(f"{target.code} defensive coordinator: {name} (from {home.code}); the two defenses swap",
                         lambda: ui.set_coordinator(self._rows, self._staff, target, home))

    def set_playbook(self, club_: Any, which: str) -> bool:
        target = ui.club(club_)
        return self._try(f"{target.code}: " + ("the new coach brings his playbook" if which == "coach"
                                               else "the club keeps its own playbook"),
                         lambda: ui.set_playbook(self._rows, self._staff, target, which))

    def reset_all(self) -> bool:
        if self._state != "disc" or not self.has_changes():
            return False
        return self._commit("Every coach back where the roster has him", ui.empty())

    # ------------------------------------------------------------------ the table and the detail
    def selected_club(self) -> ui.Club | None:
        row = self.table.currentRow()
        item = self.table.item(row, 0) if row >= 0 else None
        return None if item is None else ui.CLUBS[int(item.data(Qt.UserRole))]

    def select_club(self, club_: Any) -> bool:
        target = ui.club(club_)
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item is not None and int(item.data(Qt.UserRole)) == target.index:
                self.table.setCurrentCell(row, 0)
                return True
        return False

    def _set_state_text(self, text: str) -> None:
        self.state_label.setText(text)

    def _ask_engine(self) -> ui.EnginePlan:
        try:
            return ui.engine_plan(self._staff, self.body_provider())
        except Exception as exc:                               # noqa: BLE001 - the page keeps working without the engine's words
            return ui.EnginePlan(errors=(plain_error(exc),))

    def _schedule_engine(self) -> None:
        """Ask the build-time engine about the plan a moment after the last change, not on every click: serializing the
        roster and planning take seconds, and a burst of changes needs one answer."""

        if self._state != "disc" or not self.has_changes() or self.body_provider is None or ui.engine() is None:
            self._engine, self._engine_pending = ui.EnginePlan(), False
            self._engine_timer.stop()
            return
        self._engine, self._engine_pending = ui.EnginePlan(), True
        self._engine_timer.start()

    def _engine_due(self) -> None:
        if self.isVisible():
            self.flush_engine()                                 # a hidden page asks when it is shown again

    def flush_engine(self) -> None:
        """Ask the engine now when an answer is due (the timer, showing the page and the tests all come here)."""

        if not self._engine_pending:
            return
        self._engine_pending = False
        self._engine_timer.stop()
        self._engine = self._ask_engine()
        self._show_club()
        self._refresh_changes()

    def showEvent(self, event) -> None:  # noqa: N802 - Qt naming
        super().showEvent(event)
        if self._engine_pending:
            self._engine_timer.start()

    def _refresh(self, *, select: int | None = None) -> None:
        keep = self.selected_club().index if (select is None and self.selected_club() is not None) else select
        self._schedule_engine()
        enabled = self._state == "disc"
        for widget in (self.table, self.filter, self.reset_button, self.load_button):
            widget.setEnabled(enabled)
        self.table.blockSignals(True)
        try:
            self.table.setRowCount(0)
            seats = ui.head_seats(self._rows, self._staff) if enabled else {}
            dcs = ui.dc_seats(self._staff)
            people = ui.coordinators()
            base_names = {r.club.book: r.name for r in self._rows}
            for row in self._rows:
                book = row.club.book
                occupant = seats.get(book, ("coach", row.name))
                now = ui.occupant_name(occupant, self._staff)
                moved = occupant != ("coach", row.name)
                home = dcs.get(book, book)
                dc_changed = home != book
                dc_name = people[home].name if home in people else ""
                changes = []
                if moved:
                    changes.append("new coach" if occupant[0] == "created" else "head coach")
                if dc_changed:
                    changes.append("coordinator")
                cells = [f"{row.club.code} {row.club.nickname}", now + (f"  (was {base_names[book]})" if moved else ""),
                         dc_name + (f"  (was {people[book].name})" if dc_changed and book in people else ""),
                         ", ".join(changes)]
                index = self.table.rowCount()
                self.table.insertRow(index)
                for column, text in enumerate(cells):
                    item = QTableWidgetItem(text)
                    if column == 0:
                        item.setData(Qt.UserRole, row.club.index)
                    if changes:
                        item.setBackground(QBrush(CHANGED_BRUSH))
                    self.table.setItem(index, column, item)
        finally:
            self.table.blockSignals(False)
        self._apply_filter()
        if keep is not None:
            self.select_club(keep)
        elif self.table.rowCount():
            self.table.setCurrentCell(0, 0)
        self._show_club()
        self._refresh_changes()

    def _apply_filter(self, *_args: object) -> None:
        needle = self.filter.text().strip().casefold()
        for row in range(self.table.rowCount()):
            text = " ".join((self.table.item(row, c).text() if self.table.item(row, c) else "") for c in range(len(HEADERS)))
            self.table.setRowHidden(row, bool(needle) and needle not in text.casefold())

    def _row_for(self, club_: ui.Club) -> ui.HeadCoachRow | None:
        return next((r for r in self._rows if r.club.book == club_.book), None)

    def _show_club(self) -> None:
        club_ = self.selected_club()
        enabled = self._state == "disc" and club_ is not None
        for widget in (self.swap_button, self.hire_button, self.dc_button):
            widget.setEnabled(enabled)
        if self._state != "disc" or club_ is None:
            self._set_state_text(SOURCE_NOTE.get(self._state, ""))
            self.club_title.setText("")
            for label in (self.coach_name, self.coach_origin, self.coach_career, self.coach_style, self.coach_ratings,
                          self.dc_name, self.dc_detail):
                label.setText("")
            self.face.setPixmap(monogram("?"))
            self.playbook_check.setEnabled(False)
            return
        self._set_state_text("")
        seats = ui.head_seats(self._rows, self._staff)
        occupant = seats[club_.book]
        kind, value = occupant
        by_name = {r.name: r for r in self._rows}
        homes = ui.head_coach_homes()
        base = self._row_for(club_)
        self.club_title.setText(f"{base.display} ({club_.code})" if base and base.display else f"{club_.code} {club_.nickname}")
        if kind == "created":
            spec = ui.created_coaches(self._staff).get(value, {})
            name = ui.occupant_name(occupant, self._staff)
            self.coach_name.setText(name)
            style = spec.get("style")
            self.coach_origin.setText("A new coach you created" + (f", calling plays like the {ui.club(style).code} head coach" if style else ""))
            self.coach_career.setText("No career yet: his time starts at year 1.")
            self.coach_style.setText(f"Sideline model c{int(spec.get('body', ui.DEFAULT_BODY)):02d}")
            overall = (spec.get("ratings") or {}).get("overall")
            self.coach_ratings.setText(f"Overall {overall}" if overall is not None else "")
            self.face.setPixmap(monogram(name))
            style_ok = bool(style)
        else:
            row = by_name.get(value) or base
            self.coach_name.setText(value)
            origin_row = by_name.get(value)
            came_from = origin_row.club if origin_row is not None else None
            self.coach_origin.setText("" if came_from is None or came_from.book == club_.book
                                      else f"Came from {came_from.code} {came_from.nickname}")
            self.coach_career.setText(self._career_line(row))
            self.coach_style.setText(self._style_line(row))
            self.coach_ratings.setText(self._ratings_line(row))
            self.face.setPixmap(face_pixmap(homes.get(value), value))
            style_ok = True
        self.coach_engine.setText(self._engine_line(club_))
        arrives = occupant != ("coach", base.name if base else "")
        entry = next((e for e in self._staff.get("head_coaches", []) if ui.club(e.get("team")).book == club_.book), {})
        self.playbook_check.blockSignals(True)
        self.playbook_check.setEnabled(arrives and style_ok)
        self.playbook_check.setChecked(entry.get("playbook") == "coach")
        self.playbook_check.setToolTip(PLAYBOOK_TIP if style_ok else
                                       "A new coach can bring a playbook only when he calls plays like another coach: "
                                       "give him a play calling style when you create him.")
        self.playbook_check.blockSignals(False)
        people = ui.coordinators()
        home = ui.dc_seats(self._staff).get(club_.book, club_.book)
        dc = people.get(home)
        if dc is None:
            self.dc_name.setText("No coordinator in the Studio's 2026 data")
            self.dc_detail.setText("")
        else:
            self.dc_name.setText(dc.name + ("" if home == club_.book else f"  (from {ui.club(home).code})"))
            bits = [dc.family, f"{dc.front} front" if dc.front else "", ", ".join(dc.package)]
            self.dc_detail.setText(" · ".join(bit for bit in bits if bit))

    def _engine_line(self, club_: ui.Club) -> str:
        """What the build-time engine will do for this club (empty when there is no engine or nothing changed)."""

        info = self._engine.clubs.get(club_.book)
        if not info:
            return ""
        parts = []
        if info.get("playbook_from") not in (None, club_.book):
            parts.append(f"Plays the {ui.club(info['playbook_from']).nickname} playbook.")
        if info.get("profile"):
            names = {code: name for name, code in ui.head_coach_homes().items()}
            parts.append(f"Automatic 2026 play calling: on, the way {names.get(info['profile'], info['profile'])} calls plays.")
        elif info.get("native_reason"):
            parts.append(f"Automatic 2026 play calling: off. {info['native_reason']}.")
        return " ".join(parts)

    @staticmethod
    def _career_line(row: ui.HeadCoachRow | None) -> str:
        if row is None or not row.career:
            return ""
        c = row.career
        pieces = [f"Career {c.get('wins', 0)}-{c.get('losses', 0)}-{c.get('ties', 0)} in {c.get('total_seasons', 0)} seasons"]
        if c.get("playoff_wins", 0) or c.get("playoff_losses", 0):
            pieces.append(f"playoffs {c.get('playoff_wins', 0)}-{c.get('playoff_losses', 0)}")
        if c.get("super_bowl_wins", 0) or c.get("super_bowl_losses", 0):
            pieces.append(f"Super Bowls {c.get('super_bowl_wins', 0)} won, {c.get('super_bowl_losses', 0)} lost")
        return ", ".join(pieces)

    @staticmethod
    def _style_line(row: ui.HeadCoachRow | None) -> str:
        if row is None or not row.run_share:
            return ""
        share = row.run_share
        word = "run heavy" if share > 45 else ("pass heavy" if share < 38 else "balanced")
        return f"Play calling: {word} (runs on {share}% of plays in the game's numbers)"

    @staticmethod
    def _ratings_line(row: ui.HeadCoachRow | None) -> str:
        if row is None or not row.ratings:
            return ""
        r = row.ratings
        return (f"Overall {r.get('overall', 0)}, offense {r.get('offense', 0)}, defense {r.get('defense', 0)}, "
                f"leadership {r.get('leadership', 0)}")

    def _refresh_changes(self) -> None:
        lines = ui.describe(self._rows, self._staff) if self._state == "disc" else []
        self.changes_text.setPlainText("\n".join(lines) if lines else "No staff changes. Every club keeps the coaches on the roster.")
        found = ui.problems(self._rows, self._staff) if self._state == "disc" else []
        notes = list(found)
        if self.has_changes() and self._state == "disc":
            notes += list(self._engine.errors) + list(self._engine.notes)
            if self._engine_pending:
                notes.append("Checking this plan with the build engine...")
            if ui.engine() is None:
                notes.append("This version has no build-time staff engine yet, so a build ignores these changes until it does.")
        self.notes_text.setText("\n".join(notes))
        count = len(lines)
        self.count_label.setText(f"{count} change{'s' if count != 1 else ''}" if count else "")
        self.reset_button.setEnabled(self._state == "disc" and self.has_changes())
        self.save_button.setEnabled(self._state == "disc" and self.has_changes())

    # ------------------------------------------------------------------ the buttons
    def _swap_clicked(self) -> None:
        club_ = self.selected_club()
        if club_ is None or self._state != "disc":
            return
        seats = ui.head_seats(self._rows, self._staff)
        mine = ui.occupant_name(seats[club_.book], self._staff)
        rows = [(c.index, f"{c.code} {c.nickname} · {ui.occupant_name(seats[c.book], self._staff)}")
                for c in ui.CLUBS if c.book != club_.book and c.book in seats]

        def describe(index: int) -> str:
            other = ui.CLUBS[int(index)]
            return (f"{mine} goes to {other.code} and {ui.occupant_name(seats[other.book], self._staff)} goes to "
                    f"{club_.code}. Nobody loses a job.")

        dialog = PickDialog(f"Swap head coaches: {club_.code}", f"Swap {mine} ({club_.code}) with another club's head coach.",
                            rows, describe, self, accessible="Clubs")
        if dialog.exec_() == QDialog.Accepted and dialog.chosen() is not None:
            self.swap_clubs(club_, int(dialog.chosen()))

    def _hire_clicked(self) -> None:
        club_ = self.selected_club()
        if club_ is None or self._state != "disc":
            return
        seats = ui.head_seats(self._rows, self._staff)
        mine = ui.occupant_name(seats[club_.book], self._staff)
        employed = {value: book for book, (kind, value) in seats.items() if kind == "coach"}
        rows = []
        for row in self._rows:
            if row.name and row.name != mine:
                where = employed.get(row.name)
                rows.append((row.name, f"{row.name} · " + (f"{ui.club(where).code} head coach" if where else "let go earlier in this plan")))

        def describe(name: str) -> str:
            where = employed.get(name)
            if where is None:
                return f"{name} is hired for {club_.code}. {mine} is let go and leaves the roster."
            return (f"{name} leaves {ui.club(where).code} for {club_.code} and {mine} takes his old job at "
                    f"{ui.club(where).code}. Nobody loses a job.")

        dialog = PickDialog(f"Hire a head coach: {club_.code}",
                            f"Who coaches {club_.code}? {mine} gives up the job.", rows, describe, self, accessible="Head coaches")
        create = QPushButton("Create a new coach…")
        create.setToolTip("Make up a new head coach for this job instead.")
        wants_new = {"on": False}

        def new_clicked() -> None:
            wants_new["on"] = True
            dialog.accept()

        create.clicked.connect(new_clicked)
        dialog.extra.addWidget(create)
        dialog.extra.addStretch(1)
        if dialog.exec_() != QDialog.Accepted:
            return
        if wants_new["on"]:
            self._create_clicked(club_)
        elif dialog.chosen() is not None:
            self.move_coach(str(dialog.chosen()), club_)

    def _create_clicked(self, club_: ui.Club) -> None:
        bodies = {}
        for row in self._rows:
            if row.name and row.body not in bodies:
                bodies[row.body] = f"Model c{row.body:02d}, worn by {row.name}"
        bodies.setdefault(50, "Model c50, the game's created-team coach")
        homes = ui.head_coach_homes()
        styles = [(code, f"{name} ({code})") for name, code in sorted(homes.items(), key=lambda kv: kv[1])]
        dialog = NewCoachDialog(f"{club_.code} {club_.nickname}", bodies, styles, self)
        if dialog.exec_() == QDialog.Accepted:
            try:
                spec = dialog.spec()
            except ui.StaffUiError as exc:
                self._set_state_text(f"Refused: {exc}")
                return
            self.hire_new_coach(club_, spec)

    def _dc_clicked(self) -> None:
        club_ = self.selected_club()
        if club_ is None or self._state != "disc":
            return
        people = ui.coordinators()
        seats = ui.dc_seats(self._staff)
        holders = {home: book for book, home in seats.items()}
        mine = people.get(seats.get(club_.book, club_.book))
        rows = []
        for c in ui.CLUBS:
            dc = people.get(c.book)
            if dc is None or holders.get(c.book) == club_.book:
                continue
            rows.append((c.book, f"{dc.name} · {dc.family or 'defense'}" + (f" · now {ui.club(holders[c.book]).code}" if holders.get(c.book) else "")))

        def describe(home: str) -> str:
            who = people[home].name
            held_by = ui.club(holders[home])
            return (f"{who} runs the {club_.code} defense. {mine.name if mine else 'The current coordinator'} goes to "
                    f"{held_by.code}. The two defenses swap.")

        dialog = PickDialog(f"Change coordinator: {club_.code}", f"Who runs the {club_.code} defense?", rows, describe, self,
                            accessible="Defensive coordinators")
        if dialog.exec_() == QDialog.Accepted and dialog.chosen() is not None:
            self.set_defense(club_, str(dialog.chosen()))

    def _playbook_toggled(self, checked: bool) -> None:
        club_ = self.selected_club()
        if club_ is not None and not self._quiet:
            self.set_playbook(club_, "coach" if checked else "club")
            self._show_club()

    def _save_file(self) -> None:
        if not self.has_changes():
            return
        chosen, _filter = QFileDialog.getSaveFileName(self, "Save staff file", "staff.json", STAFF_FILTER)
        if chosen:
            ui.write_file(chosen, self._staff)
            self._set_state_text(f"Staff file saved: {Path(chosen).name}")

    def _load_file(self) -> None:
        chosen, _filter = QFileDialog.getOpenFileName(self, "Load staff file", "", STAFF_FILTER)
        if chosen:
            self.load_file(chosen)

    def load_file(self, path: Path | str) -> bool:
        """Replace the plan with a saved one after checking it against this roster; a refusal says why."""

        try:
            staff = ui.read_file(path)
        except (OSError, ValueError) as exc:
            self._set_state_text(f"Could not read that staff file: {plain_error(exc)}")
            return False
        found = ui.problems(self._rows, staff)
        if found:
            self._set_state_text("This staff file does not fit this roster: " + "; ".join(found))
            return False
        return self._commit(f"Staff file {Path(path).name} loaded", staff if not ui.is_empty(staff) else ui.empty())


__all__ = ["CoachesPanel", "NewCoachDialog", "PickDialog", "face_pixmap", "monogram"]
