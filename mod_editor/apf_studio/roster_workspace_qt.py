"""Qt panel for APF's honest 42-active-plus-11-reserve roster plan.

The panel never writes the game and never serializes source memberships.  It
is a product-facing planner for complete 53-player team concepts while the
runtime remains limited to the 42 membership pointers present in each stock
team record.
"""

from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QFrame,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .facade import ApfStudioFacade, FacadeError
from .roster_workspace import (
    FILE_EXTENSION,
    PROJECT_RESERVE_SLOTS,
    STOCK_ACTIVE_SLOTS,
    TEAM_COUNT,
    RosterWorkspace,
)


RUNTIME_BOUNDARY_NOTE = (
    "Saving this plan preserves only your eleven reserve player choices per team. "
    "Build Modded Game does not apply them. Static tracing proved the proposed "
    "in-record side table unsafe: stock APF reads and writes team bytes "
    "+0x120..+0x126, and safe extension storage remains unresolved. The next "
    "emulator-only slot-43 experiment targets one pinned test player through one "
    "exact consumer; it is not complete roster, depth-chart, or gameplay support."
)


class RosterReservePlanner(QWidget):
    """A complete 53-row planning view with an unmistakable runtime boundary."""

    def __init__(self, facade: ApfStudioFacade):
        super().__init__()
        self.facade = facade
        self._workspace: RosterWorkspace | None = None
        self._player_labels: dict[int, str] = {}
        self._team_labels: dict[int, str] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        heading = QLabel("53-player roster planner")
        heading.setObjectName("panelTitle")
        explanation = QLabel(
            "Build complete 53-player concepts for all 32 populated team records. "
            "The first 42 rows are the players APF currently sees in-game; rows "
            "43–53 are project reserves and are not written into the game yet."
        )
        explanation.setObjectName("mutedLabel")
        explanation.setWordWrap(True)
        layout.addWidget(heading)
        layout.addWidget(explanation)

        warning = QFrame()
        warning.setObjectName("warningPanel")
        warning_layout = QVBoxLayout(warning)
        warning_layout.setContentsMargins(12, 9, 12, 9)
        warning_title = QLabel("Planning only — APF still has 42 runtime slots per team")
        warning_title.setObjectName("fieldLabel")
        self.runtime_boundary_note = QLabel(RUNTIME_BOUNDARY_NOTE)
        self.runtime_boundary_note.setWordWrap(True)
        self.runtime_boundary_note.setObjectName("findingText")
        warning_layout.addWidget(warning_title)
        warning_layout.addWidget(self.runtime_boundary_note)
        layout.addWidget(warning)

        controls = QHBoxLayout()
        controls.setSpacing(8)
        controls.addWidget(QLabel("Team"))
        self.team = QComboBox()
        self.team.setMinimumWidth(250)
        self.team.setEnabled(False)
        self.team.currentIndexChanged.connect(self._team_changed)
        controls.addWidget(self.team)
        self.summary = QLabel("Load your APF game to open the planner")
        self.summary.setObjectName("countPill")
        controls.addWidget(self.summary)
        controls.addStretch(1)
        self.open_button = QPushButton("Open reserve plan…")
        self.open_button.setObjectName("secondaryButton")
        self.open_button.setEnabled(True)
        self.open_button.setToolTip(
            "Load your APF game first — Open needs a source. Click still explains."
        )
        self.open_button.setProperty(
            "disableReason",
            "Load your APF game first — Open needs a source.",
        )
        self.open_button.clicked.connect(self._open_plan)
        self.save_button = QPushButton("Save reserve plan…")
        self.save_button.setObjectName("primaryButton")
        self.save_button.setEnabled(True)
        self.save_button.setToolTip(
            "Load your APF game first — Save needs a source. Click still explains."
        )
        self.save_button.setProperty(
            "disableReason",
            "Load your APF game first — Save needs a source.",
        )
        self.save_button.clicked.connect(self._save_plan)
        controls.addWidget(self.open_button)
        controls.addWidget(self.save_button)
        layout.addLayout(controls)

        self.team_note = QLabel("")
        self.team_note.setObjectName("findingText")
        self.team_note.setWordWrap(True)
        layout.addWidget(self.team_note)

        self.table = QTableWidget(0, 4)
        self.table.setObjectName("assetTable")
        self.table.setHorizontalHeaderLabels(
            ("Roster slot", "Game visibility", "Player", "State")
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.itemSelectionChanged.connect(self._selection_changed)
        layout.addWidget(self.table, 1)

        authoring_panel = QFrame()
        authoring_panel.setObjectName("reserveEditor")
        authoring = QHBoxLayout(authoring_panel)
        authoring.setContentsMargins(10, 8, 10, 8)
        authoring.setSpacing(8)
        self.selected_slot = QLabel("Choose reserve slot 43–53")
        self.selected_slot.setObjectName("fieldLabel")
        self.player = QComboBox()
        self.player.setMinimumWidth(360)
        self.player.setEditable(True)
        self.player.setInsertPolicy(QComboBox.NoInsert)
        self.player.setEnabled(False)
        self.assign_button = QPushButton("Assign reserve")
        self.assign_button.setObjectName("primaryButton")
        self.assign_button.setEnabled(False)
        self.assign_button.clicked.connect(self._assign)
        self.clear_button = QPushButton("Clear slot")
        self.clear_button.setObjectName("dangerQuietButton")
        self.clear_button.setEnabled(False)
        self.clear_button.clicked.connect(self._clear)
        authoring.addWidget(self.selected_slot)
        authoring.addWidget(self.player, 1)
        authoring.addWidget(self.assign_button)
        authoring.addWidget(self.clear_button)
        layout.addWidget(authoring_panel)

    def set_context(self) -> None:
        """Refresh after source load; no retail-derived values are persisted here."""

        if not self.facade.source_ready:
            self._workspace = None
            self._player_labels = {}
            self._team_labels = {}
            self.team.clear()
            self.team.setEnabled(False)
            load_tip = (
                "Load your APF game first. Reserve planner Open/Save needs a "
                "source. Click still explains — buttons stay clickable."
            )
            self.open_button.setEnabled(True)
            self.save_button.setEnabled(True)
            self.open_button.setToolTip(load_tip)
            self.save_button.setToolTip(load_tip)
            self.open_button.setProperty("disableReason", load_tip)
            self.save_button.setProperty("disableReason", load_tip)
            self.table.setRowCount(0)
            self.summary.setText("Load your APF game to open the planner")
            self.team_note.setText("")
            self._selection_changed()
            return
        try:
            roster_rows = self.facade.require_inspectors().roster().model.rows
            self._workspace = self.facade.roster_workspace()
        except FacadeError as exc:
            self._workspace = None
            self.summary.setText("Planner unavailable")
            self.team_note.setText(str(exc))
            return
        self._player_labels = {
            int(row.fields["player_index"]): (
                f"#{int(row.fields['player_index']):04d} · {row.title} · "
                f"{row.fields.get('position_abbreviation', '—')}"
            )
            for row in roster_rows
            if row.kind == "player" and "player_index" in row.fields
        }
        self._team_labels = {
            int(row.fields["team_index"]): row.title
            for row in roster_rows
            if row.kind == "team"
            and 0 <= int(row.fields.get("team_index", -1)) < TEAM_COUNT
        }
        current = self.team.currentData()
        self.team.blockSignals(True)
        self.team.clear()
        for team_index in range(TEAM_COUNT):
            self.team.addItem(
                f"{team_index + 1:02d} · "
                f"{self._team_labels.get(team_index, f'Team {team_index}')}",
                team_index,
            )
        target = self.team.findData(current)
        self.team.setCurrentIndex(target if target >= 0 else 0)
        self.team.blockSignals(False)
        self.team.setEnabled(True)
        self.open_button.setEnabled(True)
        self.save_button.setEnabled(True)
        self.open_button.setToolTip(
            "Open a previously saved 32-team reserve roster plan (.json)."
        )
        self.save_button.setToolTip(
            "Save reserve player indices only (no retail game bytes)."
        )
        self.open_button.setProperty("disableReason", "")
        self.save_button.setProperty("disableReason", "")
        self._render()

    def _current_team(self) -> int:
        value = self.team.currentData()
        return int(value) if value is not None else 0

    def _team_changed(self, _index: int) -> None:
        self._render()

    def _render(self, *, select_master_slot: int | None = None) -> None:
        workspace = self._workspace
        if workspace is None:
            return
        team_index = self._current_team()
        team = workspace.teams[team_index]
        self.table.blockSignals(True)
        self.table.setRowCount(len(team.slots))
        for row_index, slot in enumerate(team.slots):
            reserve = slot.master_slot >= STOCK_ACTIVE_SLOTS
            slot_text = (
                f"{slot.master_slot + 1} · reserve {slot.master_slot - STOCK_ACTIVE_SLOTS + 1}"
                if reserve
                else f"{slot.master_slot + 1} · active"
            )
            visibility = "Not in game yet" if reserve else "Active in game"
            player = (
                "Unassigned"
                if slot.player_index is None
                else self._player_labels.get(
                    slot.player_index, f"Player #{slot.player_index:04d}"
                )
            )
            state = (
                "Project-only reserve"
                if reserve and slot.player_index is not None
                else "Open reserve slot"
                if reserve
                else "Source 42-player membership"
            )
            values = (slot_text, visibility, player, state)
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.UserRole, slot.master_slot)
                self.table.setItem(row_index, column, item)
        self.table.blockSignals(False)
        summary = workspace.summary
        self.summary.setText(
            f"{summary.assigned_project_reserve_count}/"
            f"{TEAM_COUNT * PROJECT_RESERVE_SLOTS} reserves assigned · "
            f"{summary.complete_master_team_count}/32 teams complete"
        )
        self.team_note.setText(
            (
                "Teams 25–32 use populated online-placeholder records. Their 42-player "
                "source rosters are real, but offline team-select ownership is still unproved."
                if team_index >= 24
                else "Built-in offline team · 42 source-active players plus eleven authored planning reserves."
            )
        )
        target_slot = (
            select_master_slot
            if select_master_slot is not None
            else STOCK_ACTIVE_SLOTS
        )
        if 0 <= target_slot < self.table.rowCount():
            self.table.selectRow(target_slot)
            target_item = self.table.item(target_slot, 0)
            if target_item is not None:
                self.table.scrollToItem(
                    target_item, QAbstractItemView.PositionAtTop
                )
        else:
            self.table.clearSelection()
        self._selection_changed()

    def _selected_reserve_slot(self) -> int | None:
        rows = self.table.selectionModel().selectedRows()
        if len(rows) != 1:
            return None
        master_slot = rows[0].row()
        if not STOCK_ACTIVE_SLOTS <= master_slot < STOCK_ACTIVE_SLOTS + PROJECT_RESERVE_SLOTS:
            return None
        return master_slot - STOCK_ACTIVE_SLOTS

    def _selection_changed(self) -> None:
        reserve_slot = self._selected_reserve_slot()
        workspace = self._workspace
        if reserve_slot is None or workspace is None:
            self.selected_slot.setText("Choose reserve slot 43–53")
            self.player.clear()
            self.player.setEnabled(False)
            tip = (
                "Select a reserve row (slots 43–53) after loading your APF game. "
                "Click still explains — Assign/Clear stay clickable."
                if self.facade.source_ready
                else "Load your APF game first, then select a reserve slot 43–53."
            )
            self.assign_button.setEnabled(True)
            self.clear_button.setEnabled(True)
            self.assign_button.setToolTip(tip)
            self.clear_button.setToolTip(tip)
            self.assign_button.setProperty("disableReason", tip)
            self.clear_button.setProperty("disableReason", tip)
            return
        team_index = self._current_team()
        current = workspace.teams[team_index].reserve_player_indices[reserve_slot]
        assigned = {
            value
            for team in workspace.teams
            for value in team.reserve_player_indices
            if value is not None and value != current
        }
        active = {
            value
            for team in workspace.teams
            for value in team.active_player_indices
        }
        choices = sorted(set(self._player_labels).difference(active, assigned))
        self.player.blockSignals(True)
        self.player.clear()
        for player_index in choices:
            self.player.addItem(self._player_labels[player_index], player_index)
        target = self.player.findData(current)
        if target >= 0:
            self.player.setCurrentIndex(target)
        self.player.blockSignals(False)
        self.selected_slot.setText(
            f"Team {team_index + 1} · reserve slot {reserve_slot + 1} "
            f"(master slot {STOCK_ACTIVE_SLOTS + reserve_slot + 1})"
        )
        self.player.setEnabled(bool(choices))
        assign_tip = (
            "Assign the selected player to this reserve slot."
            if choices
            else "No free players available for this reserve slot (all assigned/active)."
        )
        clear_tip = (
            "Clear this reserve slot."
            if current is not None
            else "Nothing to clear—this reserve slot is already empty."
        )
        self.assign_button.setEnabled(True)
        self.clear_button.setEnabled(True)
        self.assign_button.setToolTip(assign_tip)
        self.clear_button.setToolTip(clear_tip)
        self.assign_button.setProperty(
            "disableReason", "" if choices else assign_tip
        )
        self.clear_button.setProperty(
            "disableReason", "" if current is not None else clear_tip
        )

    def _assign(self) -> None:
        reason = str(self.assign_button.property("disableReason") or "").strip()
        if reason:
            QMessageBox.information(
                self,
                "Cannot assign reserve yet",
                reason + "\n\nFix: load game → select slot 43–53 → pick a free player.",
            )
            return
        reserve_slot = self._selected_reserve_slot()
        player_index = self.player.currentData()
        if reserve_slot is None or player_index is None:
            return
        try:
            self._workspace = self.facade.assign_roster_reserve(
                self._current_team(), reserve_slot, int(player_index)
            )
        except FacadeError as exc:
            QMessageBox.warning(self, "Reserve was not assigned", str(exc))
            return
        self._render(select_master_slot=STOCK_ACTIVE_SLOTS + reserve_slot)

    def _clear(self) -> None:
        reason = str(self.clear_button.property("disableReason") or "").strip()
        if reason:
            QMessageBox.information(
                self,
                "Cannot clear reserve yet",
                reason,
            )
            return
        reserve_slot = self._selected_reserve_slot()
        if reserve_slot is None:
            return
        try:
            self._workspace = self.facade.assign_roster_reserve(
                self._current_team(), reserve_slot, None
            )
        except FacadeError as exc:
            QMessageBox.warning(self, "Reserve was not cleared", str(exc))
            return
        self._render(select_master_slot=STOCK_ACTIVE_SLOTS + reserve_slot)

    def _open_plan(self) -> None:
        reason = str(self.open_button.property("disableReason") or "").strip()
        if reason:
            QMessageBox.information(
                self,
                "Cannot open reserve plan yet",
                reason + "\n\nFix: File → Load game, then Open reserve plan.",
            )
            return
        source, _selected_filter = QFileDialog.getOpenFileName(
            self,
            "Open APF 32-team reserve roster plan",
            str(Path.home()),
            f"APF reserve roster (*{FILE_EXTENSION})",
        )
        if not source:
            return
        try:
            self._workspace = self.facade.open_roster_reserve_plan(Path(source))
        except FacadeError as exc:
            QMessageBox.warning(self, "Reserve plan was not opened", str(exc))
            return
        self._render()

    def _save_plan(self) -> None:
        reason = str(self.save_button.property("disableReason") or "").strip()
        if reason:
            QMessageBox.information(
                self,
                "Cannot save reserve plan yet",
                reason + "\n\nFix: File → Load game, edit reserves, then Save.",
            )
            return
        destination, _selected_filter = QFileDialog.getSaveFileName(
            self,
            "Save APF 32-team reserve roster plan",
            str(Path.home() / f"apf-32-team-reserves{FILE_EXTENSION}"),
            f"APF reserve roster (*{FILE_EXTENSION})",
        )
        if not destination:
            return
        path = Path(destination)
        if path.suffix.casefold() != FILE_EXTENSION:
            path = path.with_suffix(FILE_EXTENSION)
        if path.exists() or path.is_symlink():
            QMessageBox.information(
                self,
                "Choose a new filename",
                "Reserve plans never overwrite an existing file.",
            )
            return
        try:
            saved = self.facade.save_roster_reserve_plan(path)
        except FacadeError as exc:
            QMessageBox.warning(self, "Reserve plan was not saved", str(exc))
            return
        QMessageBox.information(
            self,
            "Reserve plan saved",
            f"Saved to:\n{saved}\n\nOnly your reserve player indices are in this file. "
            "The 42 source-active memberships and all retail game bytes stay out.",
        )


__all__ = ["RosterReservePlanner"]
