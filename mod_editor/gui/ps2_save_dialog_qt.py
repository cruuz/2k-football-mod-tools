"""Modal PlayStation 2 memory-card save editor for ESPN NFL 2K5.

The dialog owns presentation, capacity feedback and edit gating only.  Reading
a save, applying a fixed-allocation edit, resealing the CRC-32 and running the
independent verifier all stay behind :class:`Ps2SaveEditorHost`, which
:class:`mod_editor.core.ps2_save_service.Ps2SaveService` implements.

Two boundaries are deliberate.  A PS2 save is the user's own file and has
nothing to do with the Xbox game image the main window may have open, so this
is a self-contained dialog rather than a page in the project workspace.  And
every name edit is *fixed allocation*: a replacement must fit the characters
the original occupies, so the dialog refuses a longer name before the writer
is ever called, and the writer refuses it again.

The source save is never modified. Output is a new ``.psu``, or -- when the
save was opened from a memory card -- a copy of that card with the edit
written into it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Protocol, runtime_checkable

from mod_editor.core.errors import ValidationError


STATUS_ALL = "all"
STATUS_EDITED = "edited"
STATUS_UNCHANGED = "unchanged"
SAVE_STATUSES = (STATUS_ALL, STATUS_EDITED, STATUS_UNCHANGED)

BOUNDARY_NOTE = (
    "FIXED-ALLOCATION EDITING  •  A replacement name must fit the characters "
    "the original used. Your source save is never changed: edits go to a new "
    "file, then an independent verifier checks them."
)

_INVALID_COLOUR = "#ff7b84"
_MODIFIED_COLOUR = "#f5c451"
_PASS_COLOUR = "#39d98a"
_TABLE_BASE = "#101827"
_TABLE_ALTERNATE = "#17243a"
_TABLE_TEXT = "#edf3fc"


# --------------------------------------------------------------------------
# Qt-free view model: everything below is testable without a QApplication.
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class PlayerNameRow:
    """One player as the table displays them, with both name slots."""

    index: int
    first: str
    last: str
    first_capacity: int
    last_capacity: int
    original_first: str
    original_last: str

    @property
    def modified(self) -> bool:
        return self.first != self.original_first or self.last != self.original_last

    def capacity_for(self, field: str) -> int:
        return self.first_capacity if field == "first" else self.last_capacity

    def value_for(self, field: str) -> str:
        return self.first if field == "first" else self.last


@dataclass(frozen=True)
class NameCapacity:
    """Allocation-aware input state for one name box."""

    used: int
    capacity: int
    valid: bool
    message: str


@dataclass(frozen=True)
class BrowserResult:
    """Rows surviving the current search and status filter."""

    rows: tuple[PlayerNameRow, ...]
    player_total: int
    edited_total: int

    @property
    def match_total(self) -> int:
        return len(self.rows)


@dataclass(frozen=True)
class Ps2SaveActionState:
    """Headless control gating shared by the dialog and its tests."""

    can_apply: bool
    can_revert_all: bool
    can_write: bool


def name_capacity(row: PlayerNameRow, field: str, value: str) -> NameCapacity:
    """Return fixed-allocation input state for a proposed name.

    Capacity is expressed in characters because that is what a person editing
    a roster can act on; the byte arithmetic stays in the save service.
    """

    if field not in ("first", "last"):
        raise ValidationError(f"A name field must be 'first' or 'last', not {field!r}.")
    capacity = row.capacity_for(field)
    used = len(value)
    if used > capacity:
        return NameCapacity(
            used,
            capacity,
            False,
            f"That name is {used} characters; this slot holds {capacity}. "
            "PS2 saves are a fixed size, so a replacement has to fit the space "
            "the old name used.",
        )
    return NameCapacity(used, capacity, True, f"{used} of {capacity} characters")


def filter_player_rows(
    rows: Iterable[PlayerNameRow], *, search: str = "", status: str = STATUS_ALL
) -> BrowserResult:
    """Narrow the roster by free text and by whether a row was edited."""

    if status not in SAVE_STATUSES:
        raise ValidationError(
            "A PS2 save status filter must be all, edited, or unchanged."
        )
    material = tuple(rows)
    needle = search.strip().casefold()
    matches = []
    for row in material:
        if status == STATUS_EDITED and not row.modified:
            continue
        if status == STATUS_UNCHANGED and row.modified:
            continue
        if needle:
            haystack = f"{row.index} {row.first} {row.last}".casefold()
            if needle not in haystack:
                continue
        matches.append(row)
    return BrowserResult(
        tuple(matches),
        len(material),
        sum(1 for row in material if row.modified),
    )


def ps2_save_action_state(
    row: PlayerNameRow | None,
    *,
    capacity: NameCapacity | None,
    save_loaded: bool,
    busy: bool,
    edit_count: int,
    changed: bool,
) -> Ps2SaveActionState:
    """Compute button gating without consulting any widget."""

    live = save_loaded and not busy
    return Ps2SaveActionState(
        can_apply=bool(live and row is not None and changed
                       and capacity is not None and capacity.valid),
        can_revert_all=bool(live and edit_count > 0),
        can_write=bool(live and edit_count > 0),
    )


def suggested_psu_name(directory: str) -> str:
    """Default filename for the Save As dialog."""

    stem = directory.strip() or "nfl2k5-ps2-save"
    return f"{stem}-edited.psu"


def suggested_card_name(directory: str) -> str:
    """Default filename when writing back into a memory-card image."""

    stem = directory.strip() or "nfl2k5-ps2-save"
    return f"{stem}-edited.ps2"


@runtime_checkable
class Ps2SaveEditorHost(Protocol):
    """The complete backend boundary consumed by the dialog."""

    @property
    def is_open(self) -> bool: ...

    @property
    def dirty(self) -> bool: ...

    @property
    def edit_count(self) -> int: ...

    def open(self, path: Path, directory: str | None = None) -> object: ...

    def summary(self) -> object: ...

    def players(self) -> list: ...

    def validate_name(self, index: int, field: str, value: str) -> str | None: ...

    def set_name(self, index: int, field: str, value: str) -> None: ...

    def revert(self) -> object: ...

    def write(self, output: Path) -> object: ...


# --------------------------------------------------------------------------
# Widgets
# --------------------------------------------------------------------------

from PyQt5.QtCore import QAbstractTableModel, QModelIndex, Qt, QTimer  # noqa: E402
from PyQt5.QtGui import QColor, QFont  # noqa: E402
from PyQt5.QtWidgets import (  # noqa: E402
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableView,
    QVBoxLayout,
    QWidget,
)

PYQT5_AVAILABLE = True


class PlayerNameTableModel(QAbstractTableModel):
    """Table over every primary player, one row per player."""

    HEADERS = ("#", "First name", "Last name", "Fits", "Status")

    def __init__(self) -> None:
        super().__init__()
        self.rows: tuple[PlayerNameRow, ...] = ()

    def set_rows(self, rows: Iterable[PlayerNameRow]) -> None:
        self.beginResetModel()
        self.rows = tuple(rows)
        self.endResetModel()

    def row_at(self, row: int) -> PlayerNameRow | None:
        if 0 <= row < len(self.rows):
            return self.rows[row]
        return None

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self.HEADERS)

    def headerData(  # noqa: N802
        self, section: int, orientation: int, role: int = Qt.DisplayRole
    ) -> object:
        if role != Qt.DisplayRole or orientation != Qt.Horizontal:
            return None
        return self.HEADERS[section]

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> object:
        if not index.isValid() or not 0 <= index.row() < len(self.rows):
            return None
        row = self.rows[index.row()]
        if role == Qt.UserRole:
            return row.index
        if role == Qt.ForegroundRole and row.modified:
            return QColor(_MODIFIED_COLOUR)
        if role == Qt.FontRole and row.modified:
            font = QFont()
            font.setBold(True)
            return font
        if role not in (Qt.DisplayRole, Qt.ToolTipRole):
            return None
        return (
            str(row.index),
            row.first,
            row.last,
            f"{row.first_capacity}/{row.last_capacity}",
            "Edited" if row.modified else "",
        )[index.column()]


class Ps2SaveEditorDialog(QDialog):
    """Open, inspect, rename, write and verify one PS2 memory-card save."""

    def __init__(
        self,
        host: Ps2SaveEditorHost | None = None,
        *,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        if host is None:
            from mod_editor.core.ps2_save_service import Ps2SaveService

            host = Ps2SaveService()
        if not isinstance(host, Ps2SaveEditorHost):
            raise TypeError(
                "PS2 save editor host does not implement Ps2SaveEditorHost"
            )
        self.host = host
        self.model = PlayerNameTableModel()
        self.selected: PlayerNameRow | None = None
        self._all_rows: tuple[PlayerNameRow, ...] = ()
        self._busy = False
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(220)
        self._search_timer.timeout.connect(self._apply_filters)

        self.setObjectName("ps2SaveEditorDialog")
        self.setWindowTitle("PS2 Save Editor")
        self.setModal(True)
        self.setMinimumSize(860, 600)
        self.resize(1020, 700)
        self._build_ui()
        self._apply_style()
        self._connect()
        self._refresh_controls()

    # -- construction --------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(12)

        header = QHBoxLayout()
        titles = QVBoxLayout()
        title = QLabel("PS2 Save Editor")
        title.setObjectName("panelTitle")
        subtitle = QLabel(
            "Edit an ESPN NFL 2K5 PlayStation 2 memory-card save. Separate "
            "from the Xbox game image in the main window."
        )
        subtitle.setObjectName("mutedLabel")
        subtitle.setWordWrap(True)
        titles.addWidget(title)
        titles.addWidget(subtitle)
        header.addLayout(titles, 1)

        self.open_file_button = QPushButton("Open Save…")
        self.open_file_button.setAccessibleName("Open a PlayStation 2 save file")
        self.open_file_button.setAccessibleDescription(
            "Choose a .psu save file or a .ps2 memory-card image to edit."
        )
        self.open_folder_button = QPushButton("Open Folder…")
        self.open_folder_button.setAccessibleName("Open an extracted save folder")
        self.open_folder_button.setAccessibleDescription(
            "Choose a folder holding an already-extracted PlayStation 2 save."
        )
        header.addWidget(self.open_file_button)
        header.addWidget(self.open_folder_button)
        root.addLayout(header)

        boundary = QLabel(BOUNDARY_NOTE)
        boundary.setObjectName("saveBoundary")
        boundary.setWordWrap(True)
        root.addWidget(boundary)

        self.info_label = QLabel("No save is open yet.")
        self.info_label.setObjectName("saveInfoCard")
        self.info_label.setWordWrap(True)
        self.info_label.setTextFormat(Qt.PlainText)
        root.addWidget(self.info_label)

        splitter = QSplitter(Qt.Horizontal)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(9)
        filters = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search players…")
        self.search.setClearButtonEnabled(True)
        self.search.setAccessibleName("Search players")
        self.search.setAccessibleDescription(
            "Filter the roster by player number or name."
        )
        self.status_filter = QComboBox()
        self.status_filter.addItem("All players", STATUS_ALL)
        self.status_filter.addItem("Edited only", STATUS_EDITED)
        self.status_filter.addItem("Unchanged only", STATUS_UNCHANGED)
        self.status_filter.setAccessibleName("Filter players by edit status")
        self.status_filter.setAccessibleDescription(
            "Show all players, only edited players, or only unchanged players."
        )
        filters.addWidget(self.search, 1)
        filters.addWidget(self.status_filter)
        left_layout.addLayout(filters)

        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setAccessibleName("Players in this save")
        self.table.setAccessibleDescription(
            "Every player in the save, with how many characters each name may use."
        )
        head = self.table.horizontalHeader()
        head.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        head.setSectionResizeMode(1, QHeaderView.Stretch)
        head.setSectionResizeMode(2, QHeaderView.Stretch)
        head.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        head.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        left_layout.addWidget(self.table, 1)
        splitter.addWidget(left)

        editor = QFrame()
        editor.setObjectName("nameEditorCard")
        editor_layout = QVBoxLayout(editor)
        editor_layout.setContentsMargins(16, 16, 16, 16)
        editor_layout.setSpacing(9)
        self.editor_title = QLabel("Select a player")
        self.editor_title.setObjectName("cardTitle")
        editor_layout.addWidget(self.editor_title)

        self.first_edit = QLineEdit()
        self.first_edit.setAccessibleName("First name")
        self.first_edit.setAccessibleDescription(
            "The player's first name. It must fit the characters shown below."
        )
        self.first_capacity_label = QLabel("")
        self.first_capacity_label.setObjectName("mutedLabel")
        self.first_capacity_label.setWordWrap(True)
        self.first_capacity_label.setTextFormat(Qt.PlainText)

        self.last_edit = QLineEdit()
        self.last_edit.setAccessibleName("Last name")
        self.last_edit.setAccessibleDescription(
            "The player's last name. It must fit the characters shown below."
        )
        self.last_capacity_label = QLabel("")
        self.last_capacity_label.setObjectName("mutedLabel")
        self.last_capacity_label.setWordWrap(True)
        self.last_capacity_label.setTextFormat(Qt.PlainText)

        editor_layout.addWidget(QLabel("First name"))
        editor_layout.addWidget(self.first_edit)
        editor_layout.addWidget(self.first_capacity_label)
        editor_layout.addWidget(QLabel("Last name"))
        editor_layout.addWidget(self.last_edit)
        editor_layout.addWidget(self.last_capacity_label)

        buttons = QHBoxLayout()
        self.apply_button = QPushButton("Apply")
        self.apply_button.setObjectName("primaryButton")
        self.apply_button.setAccessibleName("Apply this player's name change")
        self.apply_button.setAccessibleDescription(
            "Stage the edited names for this player."
        )
        self.revert_button = QPushButton("Discard All Changes")
        self.revert_button.setAccessibleName("Discard every staged change")
        self.revert_button.setAccessibleDescription(
            "Reload the save from disk, throwing away every staged edit."
        )
        buttons.addWidget(self.apply_button)
        buttons.addWidget(self.revert_button)
        buttons.addStretch(1)
        editor_layout.addLayout(buttons)
        editor_layout.addStretch(1)
        splitter.addWidget(editor)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        root.addWidget(splitter, 1)

        self.status_label = QLabel("Open a PS2 save to begin.")
        self.status_label.setObjectName("statusLabel")
        self.status_label.setTextFormat(Qt.PlainText)
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)

        self.button_box = QDialogButtonBox(QDialogButtonBox.Close)
        self.write_button = self.button_box.addButton(
            "Write .psu…", QDialogButtonBox.AcceptRole
        )
        self.write_button.setObjectName("primaryButton")
        self.write_button.setAccessibleName("Write the edited save as a .psu file")
        self.write_button.setAccessibleDescription(
            "Reseal the save, write a new .psu, and verify what changed."
        )
        root.addWidget(self.button_box)

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QDialog#ps2SaveEditorDialog QLabel#panelTitle {
                font-size: 17px; font-weight: 600;
            }
            QDialog#ps2SaveEditorDialog QLabel#mutedLabel { color: #91a0b5; }
            QDialog#ps2SaveEditorDialog QLabel#saveBoundary {
                background: #2b2410; border: 1px solid #6b5a1f;
                border-radius: 6px; padding: 9px; color: #f5c451;
            }
            QDialog#ps2SaveEditorDialog QLabel#saveInfoCard {
                background: #101827; border: 1px solid #22304a;
                border-radius: 6px; padding: 9px;
            }
            QDialog#ps2SaveEditorDialog QFrame#nameEditorCard {
                background: #101827; border: 1px solid #22304a; border-radius: 6px;
            }
            QDialog#ps2SaveEditorDialog QTableView {
                background: %s; alternate-background-color: %s; color: %s;
            }
            """
            % (_TABLE_BASE, _TABLE_ALTERNATE, _TABLE_TEXT)
        )

    def _connect(self) -> None:
        self.open_file_button.clicked.connect(self._choose_save_file)
        self.open_folder_button.clicked.connect(self._choose_save_folder)
        self.search.textChanged.connect(lambda _text: self._search_timer.start())
        self.status_filter.currentIndexChanged.connect(
            lambda _index: self._apply_filters()
        )
        self.table.selectionModel().selectionChanged.connect(
            lambda *_args: self._selection_changed()
        )
        self.first_edit.textChanged.connect(lambda _text: self._update_capacity())
        self.last_edit.textChanged.connect(lambda _text: self._update_capacity())
        self.apply_button.clicked.connect(self._apply_name)
        self.revert_button.clicked.connect(self._discard_changes)
        self.write_button.clicked.connect(self._write_psu)
        self.button_box.rejected.connect(self.reject)

    # -- opening -------------------------------------------------------

    def _choose_save_file(self) -> None:
        selected, _filter = QFileDialog.getOpenFileName(
            self,
            "Open a PlayStation 2 save",
            str(Path.home()),
            "PS2 saves (*.psu *.ps2);;PSU save (*.psu);;"
            "Memory card image (*.ps2);;All files (*)",
        )
        if selected:
            self._open_path(Path(selected))

    def _choose_save_folder(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self,
            "Open an extracted PS2 save folder",
            str(Path.home()),
            QFileDialog.ShowDirsOnly,
        )
        if selected:
            self._open_path(Path(selected))

    def _open_path(self, path: Path) -> None:
        try:
            summary = self.host.open(path)
        except Exception as exc:
            self._warn("That save could not be opened", exc)
            return
        self.selected = None
        self._reload_rows()
        self._status(f"Opened {getattr(summary, 'headline', path.name)}")

    def _reload_rows(self) -> None:
        rows: list[PlayerNameRow] = []
        try:
            for player in self.host.players():
                rows.append(
                    PlayerNameRow(
                        index=player.index,
                        first=player.first,
                        last=player.last,
                        first_capacity=player.first_capacity,
                        last_capacity=player.last_capacity,
                        original_first=player.first,
                        original_last=player.last,
                    )
                )
        except Exception as exc:
            self._warn("That save's roster could not be read", exc)
            return
        # Preserve which players differ from the file currently on disk by
        # keeping the originals from the first load of this save.
        if self._all_rows:
            originals = {row.index: (row.original_first, row.original_last)
                         for row in self._all_rows}
            rows = [
                PlayerNameRow(
                    row.index, row.first, row.last,
                    row.first_capacity, row.last_capacity,
                    *originals.get(row.index, (row.first, row.last)),
                )
                for row in rows
            ]
        self._all_rows = tuple(rows)
        summary = self.host.summary()
        self.info_label.setText(str(getattr(summary, "headline", "")))
        self._apply_filters()

    # -- browsing ------------------------------------------------------

    def _apply_filters(self) -> None:
        status = self.status_filter.currentData() or STATUS_ALL
        try:
            result = filter_player_rows(
                self._all_rows, search=self.search.text(), status=str(status)
            )
        except ValidationError as exc:
            self._status(str(exc))
            return
        self.model.set_rows(result.rows)
        if self._all_rows:
            self._status(
                f"{result.match_total:,} of {result.player_total:,} players"
                + (f" • {result.edited_total} edited" if result.edited_total else "")
            )
        self._refresh_controls()

    def _selection_changed(self) -> None:
        indexes = self.table.selectionModel().selectedRows()
        row = self.model.row_at(indexes[0].row()) if indexes else None
        self.selected = row
        if row is None:
            self.editor_title.setText("Select a player")
            self.first_edit.clear()
            self.last_edit.clear()
        else:
            self.editor_title.setText(f"Player {row.index}")
            self.first_edit.setText(row.first)
            self.last_edit.setText(row.last)
        self._update_capacity()

    # -- editing -------------------------------------------------------

    def _capacities(self) -> tuple[NameCapacity | None, NameCapacity | None]:
        row = self.selected
        if row is None:
            return None, None
        return (
            name_capacity(row, "first", self.first_edit.text()),
            name_capacity(row, "last", self.last_edit.text()),
        )

    def _update_capacity(self) -> None:
        first, last = self._capacities()
        for capacity, label in (
            (first, self.first_capacity_label),
            (last, self.last_capacity_label),
        ):
            if capacity is None:
                label.setText("")
                label.setStyleSheet("")
                continue
            label.setText(capacity.message)
            label.setStyleSheet("" if capacity.valid else f"color: {_INVALID_COLOUR};")
        self._refresh_controls()

    def _refresh_controls(self) -> None:
        first, last = self._capacities()
        row = self.selected
        changed = bool(
            row is not None
            and (self.first_edit.text() != row.first
                 or self.last_edit.text() != row.last)
        )
        both_valid = None
        if first is not None and last is not None:
            both_valid = first if not first.valid else last
        state = ps2_save_action_state(
            row,
            capacity=both_valid,
            save_loaded=self.host.is_open,
            busy=self._busy,
            edit_count=self.host.edit_count,
            changed=changed,
        )
        self.apply_button.setEnabled(state.can_apply)
        self.revert_button.setEnabled(state.can_revert_all)
        self.write_button.setEnabled(state.can_write)
        self.table.setEnabled(not self._busy)
        self.search.setEnabled(not self._busy)
        self.status_filter.setEnabled(not self._busy)

    def _apply_name(self) -> None:
        row = self.selected
        if row is None:
            return
        first, last = self._capacities()
        for capacity in (first, last):
            if capacity is not None and not capacity.valid:
                self._status(capacity.message)
                return
        try:
            if self.first_edit.text() != row.first:
                self.host.set_name(row.index, "first", self.first_edit.text())
            if self.last_edit.text() != row.last:
                self.host.set_name(row.index, "last", self.last_edit.text())
        except Exception as exc:
            self._warn("That name could not be applied", exc)
            return
        self._reload_rows()
        self._status(f"Applied player {row.index}. {self.host.edit_count} change(s) staged.")

    def _discard_changes(self) -> None:
        try:
            self.host.revert()
        except Exception as exc:
            self._warn("The save could not be reloaded", exc)
            return
        self._all_rows = ()
        self.selected = None
        self._reload_rows()
        self._status("Discarded every staged change.")

    # -- writing -------------------------------------------------------

    def _write_psu(self) -> None:
        if not self.host.is_open:
            return
        summary = self.host.summary()
        directory = str(getattr(summary, "directory", ""))
        # A save opened from a memory card can go straight back into a copy of
        # that card, which skips the import step entirely.
        from_card = bool(getattr(self.host, "opened_from_card", False))
        if from_card:
            caption = "Write the edited save to a .ps2 card or a .psu"
            suggested = suggested_card_name(directory)
            selected, _filter = QFileDialog.getSaveFileName(
                self, caption, str(Path.home() / suggested),
                "Memory card image (*.ps2);;PS2 save file (*.psu)",
            )
        else:
            caption = "Write the edited save as a .psu"
            suggested = suggested_psu_name(directory)
            selected, _filter = QFileDialog.getSaveFileName(
                self, caption, str(Path.home() / suggested), "PS2 save file (*.psu)",
            )
        if not selected:
            return
        destination = Path(selected)
        if destination.suffix.lower() not in (".psu", ".ps2"):
            destination = destination.with_suffix(".ps2" if from_card else ".psu")
        self._busy = True
        self._refresh_controls()
        try:
            result = self.host.write(destination)
        except Exception as exc:
            self._warn("That save could not be written", exc)
            return
        finally:
            self._busy = False
            self._refresh_controls()

        detail = str(getattr(result, "detail", ""))
        if getattr(result, "verified", False):
            self.status_label.setStyleSheet(f"color: {_PASS_COLOUR};")
            self._status(detail)
            QMessageBox.information(self, "PS2 save written", f"{detail}\n\n{destination}")
        else:
            self.status_label.setStyleSheet(f"color: {_INVALID_COLOUR};")
            self._status(detail)
            QMessageBox.warning(
                self,
                "PS2 save was written but did not verify",
                f"{detail}\n\nYour original save was not changed.",
            )

    # -- shared --------------------------------------------------------

    def _status(self, message: str) -> None:
        self.status_label.setText(message)
        self.status_label.setToolTip(message)

    def _warn(self, title: str, exc: Exception) -> None:
        message = str(exc).strip() or exc.__class__.__name__
        self._status(message)
        QMessageBox.warning(
            self, title, f"{message}\n\nYour original save was not changed."
        )


__all__ = [
    "BOUNDARY_NOTE",
    "BrowserResult",
    "NameCapacity",
    "PYQT5_AVAILABLE",
    "PlayerNameRow",
    "PlayerNameTableModel",
    "Ps2SaveActionState",
    "Ps2SaveEditorDialog",
    "Ps2SaveEditorHost",
    "STATUS_ALL",
    "STATUS_EDITED",
    "STATUS_UNCHANGED",
    "filter_player_rows",
    "name_capacity",
    "ps2_save_action_state",
    "suggested_card_name",
    "suggested_psu_name",
]
