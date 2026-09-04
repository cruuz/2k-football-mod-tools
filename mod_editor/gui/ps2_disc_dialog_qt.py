"""Modal PlayStation 2 disc inventory browser for ESPN NFL 2K5.

The window owns presentation and gating only.  Opening the ISO, walking its
resource packs, joining an Xbox resource-name inventory and exporting all stay
behind :class:`Ps2DiscInventoryHost`, which
:class:`mod_editor.core.ps2_disc_service.Ps2DiscService` implements.

Two boundaries are deliberate.  A PS2 disc image is the user's own file and
has nothing to do with the Xbox game image the main window may have open, so
this is a self-contained dialog rather than a page in the project workspace --
the same shape as the PS2 save editor.  And it is a *viewer*: the capability
behind it (``nfl2k5ps2.textures.disc_inventory``) is read-only-mapped, there
is no PS2 disc writer and no GS texture codec, so nothing here edits anything.
The disc is opened for reading only and only the metadata half of each
resource is ever read, so no pixel or sample can appear in this window or in
what it exports.

The table is virtualized: ~550,000 rows live in the service's SQLite sidecar
and the model fetches 256-row pages on demand, so the window opens the whole
disc without holding half a million Python objects.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Protocol, runtime_checkable

from mod_editor.core.errors import ValidationError
from mod_editor.core.ps2_disc_service import (
    PRESENCE_ANY,
    PRESENCE_BOTH,
    PRESENCE_PS2_ONLY,
    RowFilter,
)

BOUNDARY_NOTE = (
    "READ-ONLY  •  Your disc image is opened for reading and never changed. "
    "Only each resource's name and header are read; pixels and audio are never "
    "touched, so nothing here or in an export can carry game data."
)

PRESENCE_LABELS = {
    PRESENCE_ANY: "Any Xbox match",
    PRESENCE_BOTH: "Has an Xbox counterpart",
    PRESENCE_PS2_ONLY: "PS2 only",
}

_INVALID_COLOUR = "#ff7b84"
_MATCH_COLOUR = "#39d98a"
_TABLE_BASE = "#101827"
_TABLE_ALTERNATE = "#17243a"
_TABLE_TEXT = "#edf3fc"


# --------------------------------------------------------------------------
# Qt-free view model: everything below is testable without a QApplication.
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Ps2DiscActionState:
    """Headless control gating shared by the dialog and its tests."""

    can_open: bool
    can_load_xbox: bool
    can_filter: bool
    can_export_rows: bool
    can_export_report: bool


def ps2_disc_action_state(
    *, disc_open: bool, busy: bool, row_count: int
) -> Ps2DiscActionState:
    """Compute button gating without consulting any widget."""

    live = disc_open and not busy
    return Ps2DiscActionState(
        can_open=not busy,
        can_load_xbox=live,
        can_filter=live,
        can_export_rows=bool(live and row_count > 0),
        can_export_report=live,
    )


def presence_label(value: str) -> str:
    """Human wording for a presence filter value; unknown values are refused."""

    try:
        return PRESENCE_LABELS[value]
    except KeyError as exc:
        raise ValidationError(
            "An Xbox presence filter must be blank, both or ps2_only."
        ) from exc


def suggested_export_name(image_name: str, kind: str) -> str:
    """Default filename for the export pickers."""

    stem = Path(image_name.strip()).stem or "nfl2k5-ps2"
    if kind == "rows":
        return f"{stem}-inventory.csv"
    if kind == "report":
        return f"{stem}-inventory.json"
    raise ValidationError("An export is either rows or report.")


def row_status_text(shown: int, total: int, xbox_loaded: bool) -> str:
    """The footer line under the table."""

    text = f"{shown:,} of {total:,} rows"
    if not xbox_loaded:
        text += " • load an Xbox inventory to see counterparts"
    return text


@runtime_checkable
class Ps2DiscInventoryHost(Protocol):
    """The complete backend boundary consumed by the dialog."""

    OPEN_FILTER: str
    XBOX_FILTER: str

    @property
    def is_open(self) -> bool: ...

    @property
    def xbox_loaded(self) -> bool: ...

    def open(self, path: Path, progress: Optional[Callable[[str], None]] = None) -> object: ...

    def close(self) -> None: ...

    def identity(self) -> object: ...

    def summary(self) -> object: ...

    def count(self, flt: RowFilter = RowFilter()) -> int: ...

    def rows(self, flt: RowFilter, offset: int, limit: int) -> list: ...

    def distinct(self, column: str) -> list: ...

    def load_xbox_inventory(
        self, path: Path, progress: Optional[Callable[[str], None]] = None
    ) -> object: ...

    def export_csv(
        self, output: Path, flt: RowFilter = RowFilter(),
        progress: Optional[Callable[[str], None]] = None,
    ) -> int: ...

    def export_report(self, output: Path) -> Path: ...


# --------------------------------------------------------------------------
# Widgets
# --------------------------------------------------------------------------

from PyQt5.QtCore import (  # noqa: E402
    QAbstractTableModel,
    QModelIndex,
    QObject,
    QRunnable,
    Qt,
    QThreadPool,
    QTimer,
    pyqtSignal,
)
from PyQt5.QtGui import QColor  # noqa: E402
from PyQt5.QtWidgets import (  # noqa: E402
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

PYQT5_AVAILABLE = True


class _TaskSignals(QObject):
    """Cross-thread channel for one background operation."""

    result = pyqtSignal(object)
    error = pyqtSignal(str)
    stage = pyqtSignal(str)
    finished = pyqtSignal()


class _Task(QRunnable):
    """Run one host operation off the Qt thread.

    Walking a 4.6 GB disc takes a minute or two and loading an Xbox inventory
    several seconds; inside a click handler either would mark the window
    unresponsive.  ``signals`` is constructed on the Qt thread, so every
    emission from :meth:`run` is delivered as a queued call.
    """

    def __init__(self, operation: Callable[[Callable[[str], None]], object]) -> None:
        super().__init__()
        self.operation = operation
        self.signals = _TaskSignals()
        self.setAutoDelete(False)

    def run(self) -> None:
        try:
            result = self.operation(self.signals.stage.emit)
        except BaseException as exc:
            self.signals.error.emit(str(exc).strip() or exc.__class__.__name__)
        else:
            self.signals.result.emit(result)
        finally:
            self.signals.finished.emit()


class ResourceTableModel(QAbstractTableModel):
    """A paged window over the service's rows.

    ``rowCount`` is the filtered count; ``data`` fetches the 256-row page that
    holds the requested row the first time it is asked for and keeps a bounded
    number of pages.  Qt only asks for what is on screen, so opening the whole
    disc costs a count query and a page, not half a million objects.
    """

    HEADERS = ("Pack", "Entry", "Name", "Type", "Role", "Size", "Dimensions",
               "Format", "Xbox")
    PAGE = 256
    MAX_PAGES = 64

    def __init__(self) -> None:
        super().__init__()
        self._count = 0
        self._pages: dict[int, list] = {}
        self._counter: Optional[Callable[[], int]] = None
        self._fetch: Optional[Callable[[int, int], list]] = None

    def set_source(
        self,
        counter: Optional[Callable[[], int]],
        fetch: Optional[Callable[[int, int], list]],
    ) -> None:
        self.beginResetModel()
        self._pages.clear()
        self._counter = counter
        self._fetch = fetch
        self._count = counter() if counter is not None else 0
        self.endResetModel()

    def clear(self) -> None:
        self.set_source(None, None)

    def row_at(self, row: int):
        if not 0 <= row < self._count or self._fetch is None:
            return None
        page = row // self.PAGE
        rows = self._pages.get(page)
        if rows is None:
            rows = self._fetch(page * self.PAGE, self.PAGE)
            if len(self._pages) >= self.MAX_PAGES:
                self._pages.pop(next(iter(self._pages)))
            self._pages[page] = rows
        inside = row - page * self.PAGE
        return rows[inside] if inside < len(rows) else None

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else self._count

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self.HEADERS)

    def headerData(  # noqa: N802
        self, section: int, orientation: int, role: int = Qt.DisplayRole
    ) -> object:
        if role != Qt.DisplayRole or orientation != Qt.Horizontal:
            return None
        return self.HEADERS[section]

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> object:
        if not index.isValid():
            return None
        row = self.row_at(index.row())
        if row is None:
            return None
        if role == Qt.ForegroundRole and index.column() == 8 and row.xbox == PRESENCE_BOTH:
            return QColor(_MATCH_COLOUR)
        if role == Qt.ToolTipRole:
            return row.extra
        if role != Qt.DisplayRole:
            return None
        return (
            row.pack,
            str(row.entry_index),
            row.name,
            row.fourcc,
            row.role,
            row.size,
            row.dimensions,
            row.format,
            PRESENCE_LABELS.get(row.xbox, "" if not row.xbox else "not loaded"),
        )[index.column()]


class Ps2DiscInventoryDialog(QDialog):
    """Open, identity-check, browse and export one PS2 disc's resource names."""

    def __init__(
        self,
        host: Optional[Ps2DiscInventoryHost] = None,
        *,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        if host is None:
            from mod_editor.core.ps2_disc_service import Ps2DiscService

            host = Ps2DiscService()
        if not isinstance(host, Ps2DiscInventoryHost):
            raise TypeError(
                "PS2 disc inventory host does not implement Ps2DiscInventoryHost"
            )
        self.host = host
        self.model = ResourceTableModel()
        self._busy = False
        self._busy_verb = ""
        self._total_rows = 0
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(1)
        self._task: Optional[_Task] = None
        self._task_outcome: object = None
        self._task_error: Optional[str] = None
        self._task_done: Optional[Callable[[object], None]] = None
        self._task_title = ""
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(220)
        self._search_timer.timeout.connect(self._apply_filters)

        self.setObjectName("ps2DiscInventoryDialog")
        self.setWindowTitle("PS2 Disc Inventory")
        self.setModal(True)
        self.setMinimumSize(900, 620)
        self.resize(1180, 760)
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
        title = QLabel("PS2 Disc Inventory")
        title.setObjectName("panelTitle")
        subtitle = QLabel(
            "Browse every named resource on an ESPN NFL 2K5 PlayStation 2 disc "
            "and see each name's Xbox counterpart. Separate from the Xbox game "
            "image in the main window; nothing here edits anything."
        )
        subtitle.setObjectName("mutedLabel")
        subtitle.setWordWrap(True)
        titles.addWidget(title)
        titles.addWidget(subtitle)
        header.addLayout(titles, 1)

        self.open_button = QPushButton("Open Disc Image…")
        self.open_button.setAccessibleName("Open a PlayStation 2 disc image")
        self.open_button.setAccessibleDescription(
            "Choose your own SLUS-20919 ISO. It is opened read-only and inventoried."
        )
        self.xbox_button = QPushButton("Load Xbox Names…")
        self.xbox_button.setAccessibleName("Load an Xbox resource-name inventory")
        self.xbox_button.setAccessibleDescription(
            "Choose a CSV or TSV of Xbox resource names to mark each PS2 name's "
            "Xbox counterpart."
        )
        header.addWidget(self.open_button)
        header.addWidget(self.xbox_button)
        root.addLayout(header)

        boundary = QLabel(BOUNDARY_NOTE)
        boundary.setObjectName("discBoundary")
        boundary.setWordWrap(True)
        root.addWidget(boundary)

        self.info_label = QLabel("No disc image is open yet.")
        self.info_label.setObjectName("discInfoCard")
        self.info_label.setWordWrap(True)
        self.info_label.setTextFormat(Qt.PlainText)
        root.addWidget(self.info_label)

        filters = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search names or an entry number…")
        self.search.setClearButtonEnabled(True)
        self.search.setAccessibleName("Search resources")
        self.search.setAccessibleDescription(
            "Filter the inventory by resource name or outer entry number."
        )
        self.search.setProperty("studioSearch", True)
        self.type_filter = QComboBox()
        self.type_filter.setAccessibleName("Filter by resource type")
        self.role_filter = QComboBox()
        self.role_filter.setAccessibleName("Filter by row role")
        self.pack_filter = QComboBox()
        self.pack_filter.setAccessibleName("Filter by pack")
        self.presence_filter = QComboBox()
        self.presence_filter.setAccessibleName("Filter by Xbox counterpart")
        for value, label in PRESENCE_LABELS.items():
            self.presence_filter.addItem(label, value)
        filters.addWidget(self.search, 1)
        filters.addWidget(self.type_filter)
        filters.addWidget(self.role_filter)
        filters.addWidget(self.pack_filter)
        filters.addWidget(self.presence_filter)
        root.addLayout(filters)

        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setAccessibleName("Resources on this disc")
        self.table.setAccessibleDescription(
            "Every named resource: pack, entry, name, type, role, size, "
            "dimensions, GS format and whether the Xbox disc has the same name."
        )
        head = self.table.horizontalHeader()
        head.setSectionResizeMode(QHeaderView.ResizeToContents)
        head.setSectionResizeMode(2, QHeaderView.Stretch)
        root.addWidget(self.table, 1)

        footer = QHBoxLayout()
        footer.setSpacing(12)
        self.status_label = QLabel("Open a PS2 disc image to begin.")
        self.status_label.setObjectName("statusLabel")
        self.status_label.setTextFormat(Qt.PlainText)
        self.status_label.setWordWrap(True)
        footer.addWidget(self.status_label, 1)
        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("ps2ProgressBar")
        # Indeterminate: the walk reports entries done, not a byte count.
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedWidth(180)
        self.progress_bar.setAccessibleName("Operation in progress")
        self.progress_bar.hide()
        footer.addWidget(self.progress_bar, 0)
        root.addLayout(footer)

        self.button_box = QDialogButtonBox(QDialogButtonBox.Close)
        self.export_rows_button = self.button_box.addButton(
            "Export Rows (CSV)…", QDialogButtonBox.ActionRole
        )
        self.export_rows_button.setAccessibleName("Export the rows shown as CSV")
        self.export_rows_button.setAccessibleDescription(
            "Write the currently filtered rows -- names, types, sizes, offsets and "
            "dimensions only -- to a new CSV file."
        )
        self.export_report_button = self.button_box.addButton(
            "Export Report (JSON)…", QDialogButtonBox.ActionRole
        )
        self.export_report_button.setAccessibleName("Export the disc report as JSON")
        self.export_report_button.setAccessibleDescription(
            "Write the identity check, censuses and Xbox name join to a new JSON file."
        )
        root.addWidget(self.button_box)

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QDialog#ps2DiscInventoryDialog QLabel#panelTitle {
                font-size: 17px; font-weight: 600;
            }
            QDialog#ps2DiscInventoryDialog QLabel#mutedLabel { color: #91a0b5; }
            QDialog#ps2DiscInventoryDialog QLabel#discBoundary {
                background: #10261b; border: 1px solid #1f5a3a;
                border-radius: 6px; padding: 9px; color: #39d98a;
            }
            QDialog#ps2DiscInventoryDialog QLabel#discInfoCard {
                background: #101827; border: 1px solid #22304a;
                border-radius: 6px; padding: 9px;
            }
            QDialog#ps2DiscInventoryDialog QTableView {
                background: %s; alternate-background-color: %s; color: %s;
            }
            """
            % (_TABLE_BASE, _TABLE_ALTERNATE, _TABLE_TEXT)
        )

    def _connect(self) -> None:
        self.open_button.clicked.connect(self._choose_image)
        self.xbox_button.clicked.connect(self._choose_xbox_inventory)
        self.search.textChanged.connect(lambda _text: self._search_timer.start())
        for combo in (self.type_filter, self.role_filter, self.pack_filter,
                      self.presence_filter):
            combo.currentIndexChanged.connect(lambda _index: self._apply_filters())
        self.export_rows_button.clicked.connect(self._export_rows)
        self.export_report_button.clicked.connect(self._export_report)
        self.button_box.rejected.connect(self.reject)

    # -- background operations -----------------------------------------

    def _start(
        self,
        verb: str,
        title: str,
        operation: Callable[[Callable[[str], None]], object],
        done: Callable[[object], None],
    ) -> None:
        """Hand one host operation to the pool and settle when it lands."""

        self._busy = True
        self._busy_verb = verb
        self._task_title = title
        self._task_done = done
        self._task_outcome = None
        self._task_error = None
        self.status_label.setStyleSheet("")
        self._status(f"{verb}…")
        self.progress_bar.show()
        self.model.clear()
        self._refresh_controls()
        task = _Task(operation)
        self._task = task
        task.signals.stage.connect(self._status)
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

        outcome, error, done, title = (
            self._task_outcome, self._task_error, self._task_done, self._task_title,
        )
        self._task = None
        self._task_outcome = None
        self._task_error = None
        self._task_done = None
        self._busy = False
        self.progress_bar.hide()
        if error is not None:
            self._refresh_controls()
            self._apply_filters()
            self.status_label.setStyleSheet(f"color: {_INVALID_COLOUR};")
            self._status(error)
            QMessageBox.warning(
                self, title, f"{error}\n\nYour disc image was not changed."
            )
            return
        if done is not None:
            done(outcome)
        self._refresh_controls()

    # -- opening -------------------------------------------------------

    def _choose_image(self) -> None:
        selected, _filter = QFileDialog.getOpenFileName(
            self, "Open a PlayStation 2 disc image", str(Path.home()),
            self.host.OPEN_FILTER,
        )
        if selected:
            self._open_path(Path(selected))

    def _open_path(self, path: Path) -> None:
        if self._busy:
            return
        self._total_rows = 0
        self.info_label.setText(f"Reading {path.name}…")
        self._start(
            "Inventorying the disc",
            "That disc image could not be inventoried",
            lambda stage: self.host.open(path, stage),
            self._opened,
        )

    def _opened(self, _identity: object) -> None:
        self._populate_filters()
        self._refresh_info()
        self._apply_filters()

    def _populate_filters(self) -> None:
        for combo, column, label in (
            (self.type_filter, "fourcc", "All types"),
            (self.role_filter, "role", "All roles"),
            (self.pack_filter, "pack", "All packs"),
        ):
            combo.blockSignals(True)
            combo.clear()
            combo.addItem(label, "")
            try:
                for value in self.host.distinct(column):
                    combo.addItem(value, value)
            except Exception as exc:  # pragma: no cover - defensive
                self._status(str(exc))
            combo.blockSignals(False)
        self.presence_filter.blockSignals(True)
        self.presence_filter.setCurrentIndex(0)
        self.presence_filter.blockSignals(False)

    def _refresh_info(self) -> None:
        if not self.host.is_open:
            self.info_label.setText("No disc image is open yet.")
            return
        identity = self.host.identity()
        summary = self.host.summary()
        self._total_rows = int(getattr(summary, "rows", 0))
        lines = [str(getattr(identity, "headline", "")), str(getattr(summary, "headline", ""))]
        if not getattr(identity, "serial_matches", True):
            lines.append(
                "This is not the SLUS-20919 boot serial the studio supports; the "
                "inventory still ran, but names may not line up with the Xbox disc."
            )
        elif not getattr(identity, "retail_boot_elf", True):
            lines.append(
                "The boot ELF differs from the retail digest: a modified disc. "
                "The inventory still ran and is reported as such."
            )
        self.info_label.setText("\n".join(line for line in lines if line))

    # -- the Xbox side -------------------------------------------------

    def _choose_xbox_inventory(self) -> None:
        if self._busy or not self.host.is_open:
            return
        selected, _filter = QFileDialog.getOpenFileName(
            self, "Load an Xbox resource-name inventory", str(Path.home()),
            self.host.XBOX_FILTER,
        )
        if selected:
            self._load_xbox_path(Path(selected))

    def _load_xbox_path(self, path: Path) -> None:
        self._start(
            "Joining the Xbox names",
            "That inventory could not be joined",
            lambda stage: self.host.load_xbox_inventory(path, stage),
            self._xbox_loaded,
        )

    def _xbox_loaded(self, _summary: object) -> None:
        self._refresh_info()
        self._apply_filters()

    # -- filtering -----------------------------------------------------

    def _current_filter(self) -> RowFilter:
        return RowFilter(
            search=self.search.text(),
            fourcc=str(self.type_filter.currentData() or ""),
            role=str(self.role_filter.currentData() or ""),
            pack=str(self.pack_filter.currentData() or ""),
            presence=str(self.presence_filter.currentData() or ""),
        )

    def _apply_filters(self) -> None:
        if self._busy or not self.host.is_open:
            self.model.clear()
            self._refresh_controls()
            return
        flt = self._current_filter()
        try:
            flt.validate()
        except ValidationError as exc:
            self._status(str(exc))
            return
        self.model.set_source(
            lambda: self.host.count(flt),
            lambda offset, limit: self.host.rows(flt, offset, limit),
        )
        self.status_label.setStyleSheet("")
        self._status(row_status_text(
            self.model.rowCount(), self._total_rows, bool(self.host.xbox_loaded)
        ))
        self._refresh_controls()

    def _refresh_controls(self) -> None:
        state = ps2_disc_action_state(
            disc_open=self.host.is_open, busy=self._busy,
            row_count=self.model.rowCount(),
        )
        self.open_button.setEnabled(state.can_open)
        self.xbox_button.setEnabled(state.can_load_xbox)
        self.search.setEnabled(state.can_filter)
        for combo in (self.type_filter, self.role_filter, self.pack_filter):
            combo.setEnabled(state.can_filter)
        self.presence_filter.setEnabled(state.can_filter and bool(self.host.xbox_loaded))
        self.table.setEnabled(not self._busy)
        self.export_rows_button.setEnabled(state.can_export_rows)
        self.export_report_button.setEnabled(state.can_export_report)

    # -- exporting -----------------------------------------------------

    def _export_rows(self) -> None:
        if self._busy or not self.host.is_open:
            return
        flt = self._current_filter()
        suggested = suggested_export_name(self.host.identity().name, "rows")
        selected, _filter = QFileDialog.getSaveFileName(
            self, "Export the rows shown as CSV", str(Path.home() / suggested),
            "CSV (*.csv)", options=QFileDialog.DontConfirmOverwrite,
        )
        if not selected:
            return
        destination = Path(selected)
        if destination.suffix.lower() != ".csv":
            destination = destination.with_suffix(".csv")
        self._start(
            "Exporting rows",
            "The rows could not be exported",
            lambda stage: self.host.export_csv(destination, flt, stage),
            lambda written: self._exported(f"Exported {written:,} rows to {destination}"),
        )

    def _export_report(self) -> None:
        if self._busy or not self.host.is_open:
            return
        suggested = suggested_export_name(self.host.identity().name, "report")
        selected, _filter = QFileDialog.getSaveFileName(
            self, "Export the disc report as JSON", str(Path.home() / suggested),
            "JSON (*.json)", options=QFileDialog.DontConfirmOverwrite,
        )
        if not selected:
            return
        destination = Path(selected)
        if destination.suffix.lower() != ".json":
            destination = destination.with_suffix(".json")
        self._start(
            "Exporting the report",
            "The report could not be exported",
            lambda _stage: self.host.export_report(destination),
            lambda written: self._exported(f"Wrote the report to {written}"),
        )

    def _exported(self, message: str) -> None:
        self._apply_filters()
        self.status_label.setStyleSheet(f"color: {_MATCH_COLOUR};")
        self._status(message)

    # -- shared --------------------------------------------------------

    def done(self, result: int) -> None:
        """Refuse to close while an operation is in flight; release the sidecar otherwise."""

        if self._busy:
            self._status(f"{self._busy_verb} is still running. It will finish in a moment.")
            return
        try:
            self.host.close()
        except Exception:  # pragma: no cover - closing must never block the window
            pass
        super().done(result)

    def _status(self, message: str) -> None:
        self.status_label.setText(message)
        self.status_label.setToolTip(message)


__all__ = [
    "BOUNDARY_NOTE",
    "PRESENCE_LABELS",
    "PYQT5_AVAILABLE",
    "Ps2DiscActionState",
    "Ps2DiscInventoryDialog",
    "Ps2DiscInventoryHost",
    "ResourceTableModel",
    "presence_label",
    "ps2_disc_action_state",
    "row_status_text",
    "suggested_export_name",
]
