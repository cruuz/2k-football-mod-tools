"""The "Select other games…" dialog: core-owned, contract-driven, game-blind.

Draws :mod:`mod_editor.games.chooser`: **one row per game, the studio it
opens**.  Open opens that module's ``studio_window``; the module's other
windows are reachable by id, from the command line and from the studio's own
Windows menu, but the chooser asks only which game.  The studio's File menu
needs exactly one action and one handler to host every game module through
this window::

    action = file_menu.addAction("Select other games…")
    action.triggered.connect(self._open_game_chooser)

    def _open_game_chooser(self, _checked=False):
        from mod_editor.games.chooser_qt import GameChooserDialog
        dialog = GameChooserDialog(parent=self, context={"facade": self.facade})
        dialog.exec_()
        dialog.deleteLater()

Nothing here knows a game.  A module that cannot be loaded is a row that says
why and cannot be opened; a module whose window fails to open reports the
sentence in the detail pane.  The dialog never raises out of a click.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import DiscoveryReport, discover
from .chooser import (
    BOUNDARY_NOTE,
    ChooserRow,
    chooser_headline,
    chooser_rows,
    open_studio,
    open_window,
)
from .contract import Refusal

COLUMNS = ("Studio", "Status", "Detail")
_PROBLEM_COLOUR = "#ff7b84"


class GameChooserDialog(QDialog):
    """List every discovered game's studio and open the one the user picks."""

    def __init__(
        self,
        report: Optional[DiscoveryReport] = None,
        *,
        parent: Optional[QWidget] = None,
        context: Optional[Mapping[str, Any]] = None,
        games_root: Optional[Path] = None,
        modal_windows: bool = True,
    ) -> None:
        super().__init__(parent)
        self._report = report if report is not None else discover(games_root)
        self._rows: tuple[ChooserRow, ...] = chooser_rows(self._report)
        self._context = dict(context or {})
        self._modal_windows = modal_windows
        self.last_opened: Any = None
        self.setObjectName("gameChooserDialog")
        self.setWindowTitle("Select other games")
        self.setModal(True)
        self.setMinimumSize(720, 420)
        self._build_ui()
        self._populate()

    # -- construction --------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        self.headline = QLabel(chooser_headline(self._rows))
        self.headline.setObjectName("gameChooserHeadline")
        self.headline.setAccessibleName("Game modules summary")
        layout.addWidget(self.headline)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setObjectName("gameChooserTable")
        self.table.setAccessibleName("Game studios")
        self.table.setAccessibleDescription(
            "Every installed game's studio, with what it is and whether it can be opened."
        )
        self.table.setHorizontalHeaderLabels(list(COLUMNS))
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.itemSelectionChanged.connect(self._selection_changed)
        self.table.itemDoubleClicked.connect(lambda _item: self.open_selected())
        layout.addWidget(self.table, 2)

        self.detail = QLabel("")
        self.detail.setObjectName("gameChooserDetail")
        self.detail.setAccessibleName("Selected module detail")
        self.detail.setWordWrap(True)
        self.detail.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.detail)

        note = QLabel(BOUNDARY_NOTE)
        note.setObjectName("gameChooserBoundaryNote")
        note.setWordWrap(True)
        layout.addWidget(note)

        self.buttons = QDialogButtonBox()
        self.open_button = self.buttons.addButton("Open studio", QDialogButtonBox.AcceptRole)
        self.open_button.setObjectName("gameChooserOpen")
        self.open_button.setAccessibleName("Open the selected studio")
        self.open_button.setEnabled(False)
        self.open_button.clicked.connect(lambda _checked=False: self.open_selected())
        close_button = self.buttons.addButton(QDialogButtonBox.Close)
        close_button.clicked.connect(self.reject)
        layout.addWidget(self.buttons)

    def _populate(self) -> None:
        self.table.setRowCount(len(self._rows))
        for index, row in enumerate(self._rows):
            values = (row.studio_label, row.status_text, row.detail)
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.UserRole, row.game_id)
                if not row.loadable:
                    item.setForeground(Qt.gray)
                self.table.setItem(index, column, item)
        self.table.resizeColumnsToContents()
        if self._rows:
            self.table.selectRow(0)

    # -- state ---------------------------------------------------------

    def rows(self) -> tuple[ChooserRow, ...]:
        return self._rows

    def selected_row(self) -> Optional[ChooserRow]:
        indexes = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        if not indexes:
            return None
        position = indexes[0].row()
        return self._rows[position] if 0 <= position < len(self._rows) else None

    def select_game(self, game_id: str) -> bool:
        for index, row in enumerate(self._rows):
            if row.game_id == game_id:
                self.table.selectRow(index)
                return True
        return False

    def _selection_changed(self) -> None:
        row = self.selected_row()
        if row is None:
            self.detail.setText("")
            self.open_button.setEnabled(False)
            return
        self.detail.setStyleSheet("" if row.loadable else f"color: {_PROBLEM_COLOUR};")
        self.detail.setText(row.detail)
        self.open_button.setEnabled(row.loadable)

    # -- opening -------------------------------------------------------

    def open_selected(self, window_id: Optional[str] = None) -> bool:
        """Open the selected studio -- or one named window -- through the module.

        Every failure is reported in the detail pane; the dialog never raises
        out of a click.  ``window_id`` is how the studio's own Windows menu and
        the command line reach a module's other windows through this same path.
        """

        row = self.selected_row()
        if row is None or not row.loadable:
            return False
        chosen = window_id or row.studio_window
        try:
            if window_id:
                window = open_window(self._report, row.game_id, window_id, parent=self,
                                     context=self._context)
            else:
                window = open_studio(self._report, row.game_id, parent=self, context=self._context)
        except Refusal as exc:
            self.detail.setStyleSheet(f"color: {_PROBLEM_COLOUR};")
            self.detail.setText(str(exc))
            return False
        self.last_opened = window
        self.detail.setStyleSheet("")
        self.detail.setText(f"{row.studio_label}: opened {chosen}.")
        if self._modal_windows and hasattr(window, "exec_"):
            window.exec_()
            if hasattr(window, "deleteLater"):
                window.deleteLater()
        elif hasattr(window, "show"):
            window.show()
        return True


__all__ = ["COLUMNS", "GameChooserDialog"]
