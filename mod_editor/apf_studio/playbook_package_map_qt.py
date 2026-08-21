"""Who lines up: edit the 11-role package map on each MASTER formation."""

from __future__ import annotations

from typing import Callable

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mod_editor.core.apf2k8_package_map_writer import (
    APF_PACKAGE_MAP_ROLE_TE,
    APF_PACKAGE_MAP_ROLE_WR3,
    HONESTY,
    PackageMapChange,
    list_apf_formations,
    put_role_in_slot,
    role_label,
    slot_summary,
    swap_te_and_wr,
)
from mod_editor.core.apf2k8_playbook_route_writer import read_master_play_body
from mod_editor.core.errors import ValidationError


TaskRunner = Callable[..., bool]

TABLE_FG = QColor("#dce8f5")
TABLE_BG = QColor("#0c1421")


class ApfPackageMapPanel(QWidget):
    """Per-formation role map. Project stores indexes, never retail bytes."""

    modifiedChanged = pyqtSignal()

    def __init__(self, facade: object, run_task: TaskRunner):
        super().__init__()
        self.facade = facade
        self.run_task = run_task
        self._source_rows: tuple[tuple[int, str, tuple[int, ...]], ...] = ()
        self._draft: dict[int, tuple[int, ...]] = {}
        self._draft_error: str | None = None
        self._draft_error_message: str | None = None
        self._loading = False

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(10)
        title = QLabel("Who lines up")
        title.setObjectName("panelTitle")
        explanation = QLabel(
            "Each formation has 11 on-field slots. This map assigns a role to "
            "each slot. Role 8 is TE. Role 9 is WR. The other roles are "
            "numbered until we prove their names.\n\n"
            "This does not change which formation the CPU picks on 3rd-and-long. "
            "Whether the game's on-field look changes at runtime is unproved. "
            "Build, then check it in Xenia."
        )
        explanation.setObjectName("findingText")
        explanation.setWordWrap(True)
        root.addWidget(title)
        root.addWidget(explanation)

        columns = QHBoxLayout()
        columns.setSpacing(14)
        left = QVBoxLayout()
        left.addWidget(QLabel("Formations"))
        self.formation_list = QListWidget()
        self.formation_list.setObjectName("assetList")
        self.formation_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.formation_list.currentItemChanged.connect(
            lambda _current, _previous: self._refresh_map()
        )
        left.addWidget(self.formation_list, 1)
        columns.addLayout(left, 2)

        right = QVBoxLayout()
        self.map_header = QLabel("On-field slots")
        self.map_header.setWordWrap(True)
        right.addWidget(self.map_header)
        self.table = QTableWidget(0, 3)
        self.table.setObjectName("assetTable")
        self.table.setHorizontalHeaderLabels(("Slot", "Role", "Proved name"))
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        right.addWidget(self.table, 1)

        actions = QHBoxLayout()
        self.put_te = QPushButton("Put TE in selected slot")
        self.put_wr = QPushButton("Put WR in selected slot")
        self.swap_te_wr = QPushButton("Swap TE and WR")
        self.copy_from = QComboBox()
        self.copy_button = QPushButton("Copy map from…")
        for button in (self.put_te, self.put_wr, self.swap_te_wr, self.copy_button):
            button.setObjectName("quietButton")
        self.put_te.clicked.connect(lambda: self._put_role(APF_PACKAGE_MAP_ROLE_TE))
        self.put_wr.clicked.connect(lambda: self._put_role(APF_PACKAGE_MAP_ROLE_WR3))
        self.swap_te_wr.clicked.connect(self._swap_te_wr)
        self.copy_button.clicked.connect(self._copy_from)
        actions.addWidget(self.put_te)
        actions.addWidget(self.put_wr)
        actions.addWidget(self.swap_te_wr)
        actions.addStretch(1)
        right.addLayout(actions)
        copy_row = QHBoxLayout()
        copy_row.addWidget(QLabel("Donor formation"))
        copy_row.addWidget(self.copy_from, 1)
        copy_row.addWidget(self.copy_button)
        right.addLayout(copy_row)

        commit = QHBoxLayout()
        self.revert_button = QPushButton("Revert this formation")
        self.revert_button.setObjectName("dangerQuietButton")
        self.revert_all_button = QPushButton("Revert all who-lines-up")
        self.revert_all_button.setObjectName("dangerQuietButton")
        self.stage_button = QPushButton("Stage this map")
        self.stage_button.setObjectName("primaryButton")
        self.revert_button.clicked.connect(self._revert_one)
        self.revert_all_button.clicked.connect(self._revert_all)
        self.stage_button.clicked.connect(self._stage)
        commit.addStretch(1)
        commit.addWidget(self.revert_button)
        commit.addWidget(self.revert_all_button)
        commit.addWidget(self.stage_button)
        right.addLayout(commit)
        columns.addLayout(right, 3)
        root.addLayout(columns, 1)

        note = QLabel(HONESTY)
        note.setObjectName("findingText")
        note.setWordWrap(True)
        root.addWidget(note)
        self.status = QLabel("Load a game to read the formation maps.")
        self.status.setObjectName("mutedLabel")
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        self.set_context()

    def set_context(self) -> None:
        if not bool(getattr(self.facade, "source_ready", False)):
            self._source_rows = ()
            self._draft = {}
            self._draft_error = None
            self._draft_error_message = None
            self._set_commit_enabled(False)
            self.formation_list.clear()
            self.copy_from.clear()
            self.table.setRowCount(0)
            self.status.setText("Load a game to read the formation maps.")
            return
        source = getattr(self.facade, "source", None)
        index_0a = getattr(source, "index_0a", None) if source is not None else None
        if index_0a is None:
            self.status.setText("Load a game to read the formation maps.")
            return
        try:
            body = read_master_play_body(index_0a)
            self._source_rows = list_apf_formations(body)
        except Exception as exc:
            self._source_rows = ()
            self._draft = {}
            self._draft_error = None
            self._draft_error_message = None
            self._set_commit_enabled(False)
            self.status.setText(f"Could not read formations: {exc}")
            return
        self._restore_draft()
        self._reload_formation_list()
        self._refresh_map()
        self._update_status()

    def _set_commit_enabled(self, enabled: bool) -> None:
        self.stage_button.setEnabled(enabled)
        self.revert_button.setEnabled(enabled)
        self.revert_all_button.setEnabled(enabled)

    def _restore_draft(self) -> bool:
        """Sync the draft with the staged set. Never wipes the draft silently:
        on any read failure the draft stays as shown and every commit path is
        disabled until the next successful sync."""

        reader = getattr(self.facade, "staged_package_maps", None)
        staged: dict[int, tuple[int, ...]] = {}
        if reader is not None:
            try:
                for change in reader():
                    staged[int(change.formation_index)] = tuple(change.new_map)
            except Exception as exc:
                self._draft_error = str(exc)
                self._draft_error_message = (
                    "Could not read the staged who-lines-up edits "
                    f"({exc}). Nothing will be staged until this panel "
                    "reloads cleanly."
                )
                self._set_commit_enabled(False)
                self.status.setText(self._draft_error_message)
                return False
        self._draft_error = None
        self._draft_error_message = None
        self._draft = staged
        self._set_commit_enabled(True)
        return True

    def _reload_formation_list(self) -> None:
        previous = self._selected_index()
        self.formation_list.clear()
        self.copy_from.clear()
        for index, name, source_map in self._source_rows:
            current = self._draft.get(index, source_map)
            mark = "  · edited" if current != source_map else ""
            item = QListWidgetItem(f"{name}{mark}")
            item.setData(Qt.UserRole, index)
            self.formation_list.addItem(item)
            self.copy_from.addItem(name, index)
        if previous is not None:
            for row in range(self.formation_list.count()):
                item = self.formation_list.item(row)
                if item is not None and item.data(Qt.UserRole) == previous:
                    self.formation_list.setCurrentRow(row)
                    break
        elif self.formation_list.count():
            self.formation_list.setCurrentRow(0)

    def _selected_index(self) -> int | None:
        item = self.formation_list.currentItem()
        if item is None:
            return None
        value = item.data(Qt.UserRole)
        return int(value) if type(value) is int else None

    def _source_map(self, formation_index: int) -> tuple[int, ...]:
        for index, _name, package_map in self._source_rows:
            if index == formation_index:
                return package_map
        raise ValidationError(f"Unknown formation {formation_index}.")

    def _current_map(self, formation_index: int) -> tuple[int, ...]:
        return self._draft.get(formation_index, self._source_map(formation_index))

    def _refresh_map(self) -> None:
        formation_index = self._selected_index()
        self.table.setRowCount(0)
        if formation_index is None:
            self.map_header.setText("On-field slots")
            return
        name = next(
            title for index, title, _map in self._source_rows if index == formation_index
        )
        package_map = self._current_map(formation_index)
        self.map_header.setText(f"{name} — {slot_summary(package_map)}")
        self.table.setRowCount(len(package_map))
        for slot, role in enumerate(package_map):
            values = (str(slot + 1), str(int(role)), role_label(int(role)))
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setForeground(TABLE_FG)
                item.setBackground(TABLE_BG)
                self.table.setItem(slot, column, item)

    def _set_draft(self, formation_index: int, package_map: tuple[int, ...]) -> None:
        source = self._source_map(formation_index)
        if package_map == source:
            self._draft.pop(formation_index, None)
        else:
            self._draft[formation_index] = package_map
        self._reload_formation_list()
        self._refresh_map()
        self._update_status()

    def _put_role(self, role: int) -> None:
        formation_index = self._selected_index()
        if formation_index is None:
            QMessageBox.information(
                self, "Pick a formation", "Select a formation, then a slot."
            )
            return
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(
                self,
                "Pick a slot",
                "Select the on-field slot that should get that role.",
            )
            return
        try:
            updated = put_role_in_slot(self._current_map(formation_index), row, role)
        except ValidationError as exc:
            QMessageBox.information(self, "That swap is not legal", str(exc))
            return
        self._set_draft(formation_index, updated)

    def _swap_te_wr(self) -> None:
        formation_index = self._selected_index()
        if formation_index is None:
            QMessageBox.information(self, "Pick a formation", "Select a formation first.")
            return
        try:
            updated = swap_te_and_wr(self._current_map(formation_index))
        except ValidationError as exc:
            QMessageBox.information(self, "That swap is not legal", str(exc))
            return
        self._set_draft(formation_index, updated)

    def _copy_from(self) -> None:
        formation_index = self._selected_index()
        donor = self.copy_from.currentData()
        if formation_index is None:
            QMessageBox.information(self, "Pick a formation", "Select a formation first.")
            return
        if type(donor) is not int:
            QMessageBox.information(
                self, "Pick a donor", "Choose the formation to copy the map from."
            )
            return
        if donor == formation_index:
            QMessageBox.information(
                self, "Choose a different formation", "Donor and target must differ."
            )
            return
        self._set_draft(formation_index, self._current_map(int(donor)))

    def _stage(self) -> None:
        if not bool(getattr(self.facade, "source_ready", False)):
            QMessageBox.information(
                self, "Load a game first", "Who lines up needs MASTER PLAY from your game."
            )
            return
        if self._draft_error is not None:
            QMessageBox.information(
                self,
                "Reload the panel",
                "The staged edits could not be read back, so staging is "
                "disabled. Switch tabs or reopen the game to reload.",
            )
            return
        if not self._draft:
            self.status.setText(
                "Nothing to stage yet. Select a formation and move TE or WR."
            )
            return
        changes = [
            PackageMapChange(index, package_map)
            for index, package_map in sorted(self._draft.items())
        ]
        apply = getattr(self.facade, "apply_package_maps", None)
        if apply is None:
            return
        message = (
            f"{len(changes)} formation map{'s' if len(changes) != 1 else ''} staged."
        )
        self.run_task(
            "Staging who-lines-up maps",
            lambda progress: apply(changes, progress=progress),
            lambda result: self._after_stage(
                result, message, "Those maps were already staged; nothing changed."
            ),
            True,
        )

    def _revert_one(self) -> None:
        formation_index = self._selected_index()
        if formation_index is None:
            QMessageBox.information(self, "Pick a formation", "Select a formation first.")
            return
        if self._draft_error is not None:
            QMessageBox.information(
                self,
                "Reload the panel",
                "The staged edits could not be read back, so reverting is "
                "disabled. Switch tabs or reopen the game to reload.",
            )
            return
        self._draft.pop(formation_index, None)
        self._commit_draft()

    def _revert_all(self) -> None:
        if self._draft_error is not None:
            QMessageBox.information(
                self,
                "Reload the panel",
                "The staged edits could not be read back, so reverting is "
                "disabled. Switch tabs or reopen the game to reload.",
            )
            return
        if not self._draft:
            self.status.setText("Nothing is staged, so there is nothing to revert.")
            return
        answer = QMessageBox.question(
            self,
            "Revert every who-lines-up edit?",
            "This unstages every formation map you edited. The game files "
            "were never touched. Continue?",
        )
        if answer != QMessageBox.Yes:
            return
        self._draft = {}
        self._commit_draft()

    def _commit_draft(self) -> None:
        apply = getattr(self.facade, "apply_package_maps", None)
        if apply is None or not bool(getattr(self.facade, "source_ready", False)):
            self._reload_formation_list()
            self._refresh_map()
            self._update_status()
            return
        changes = [
            PackageMapChange(index, package_map)
            for index, package_map in sorted(self._draft.items())
        ]
        self.run_task(
            "Updating who-lines-up maps",
            lambda progress: apply(changes, progress=progress),
            lambda result: self._after_stage(
                result,
                "Who-lines-up maps updated.",
                "Who-lines-up maps already match; nothing changed.",
            ),
            True,
        )

    def _after_stage(self, result: object, message: str, unchanged_message: str) -> None:
        restored = self._restore_draft()
        self._reload_formation_list()
        self._refresh_map()
        if restored:
            chosen = message if result else unchanged_message
            self.status.setText(chosen + " " + HONESTY)
        self.modifiedChanged.emit()

    def _update_status(self) -> None:
        if self._draft_error_message is not None:
            self.status.setText(self._draft_error_message)
            return
        if not self._source_rows:
            self.status.setText("Load a game to read the formation maps.")
            return
        count = len(self._draft)
        if count:
            self.status.setText(
                f"{count} formation map{'s' if count != 1 else ''} ready to stage "
                "or already staged. Build writes them into the copied game folder."
            )
        else:
            self.status.setText(
                f"{len(self._source_rows)} formations. Select one and move TE or WR."
            )

    def refresh(self) -> None:
        if bool(getattr(self.facade, "source_ready", False)) and self._source_rows:
            self._restore_draft()
            self._reload_formation_list()
            self._refresh_map()
            self._update_status()
        else:
            self.set_context()


__all__ = ["ApfPackageMapPanel"]
