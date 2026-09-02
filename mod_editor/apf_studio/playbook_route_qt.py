"""Qt editor for exact stock APF PLAY assignment-route copies and swaps."""

from __future__ import annotations

from typing import Callable

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mod_editor.core.apf2k8_playbook_route_writer import (
    PROVIDER_KIND,
    ROUTE_ORPHAN_MESSAGE,
)

from .inspectors import PagedModel


TaskRunner = Callable[..., bool]


class PlayAssignmentRoutePanel(QWidget):
    """Donor/target picker whose project stores logical coordinates only."""

    modifiedChanged = pyqtSignal()

    def __init__(self, facade: object, run_task: TaskRunner):
        super().__init__()
        self.facade = facade
        self.run_task = run_task
        self._plays: tuple[tuple[int, str], ...] = ()

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(10)
        title = QLabel("Stock assignment route editor")
        title.setObjectName("panelTitle")
        explanation = QLabel(
            "Copy or swap one of the 11 player-assignment routes between stock "
            "plays. Copy keeps both routes only when the target's current route "
            "is also used elsewhere. If Copy refuses, use Swap — that trades "
            "the two routes and deletes nothing. The project stores play and "
            "slot numbers, not retail bytes."
        )
        explanation.setObjectName("findingText")
        explanation.setWordWrap(True)
        root.addWidget(title)
        root.addWidget(explanation)

        picker = QFrame()
        picker.setObjectName("panel")
        grid = QGridLayout(picker)
        grid.setContentsMargins(14, 12, 14, 12)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        grid.addWidget(QLabel("TARGET PLAY"), 0, 0)
        grid.addWidget(QLabel("TARGET PLAYER SLOT"), 0, 1)
        grid.addWidget(QLabel("DONOR PLAY"), 2, 0)
        grid.addWidget(QLabel("DONOR PLAYER SLOT"), 2, 1)
        self.target_play = QComboBox()
        self.target_slot = QComboBox()
        self.donor_play = QComboBox()
        self.donor_slot = QComboBox()
        for combo in (self.target_slot, self.donor_slot):
            for slot in range(11):
                combo.addItem(f"Slot {slot + 1}", slot)
        for combo in (
            self.target_play,
            self.target_slot,
            self.donor_play,
            self.donor_slot,
        ):
            combo.currentIndexChanged.connect(lambda _index: self._update_buttons())
        grid.addWidget(self.target_play, 1, 0)
        grid.addWidget(self.target_slot, 1, 1)
        grid.addWidget(self.donor_play, 3, 0)
        grid.addWidget(self.donor_slot, 3, 1)
        buttons = QHBoxLayout()
        self.copy_button = QPushButton("Copy donor route to target")
        self.copy_button.setObjectName("primaryButton")
        self.swap_button = QPushButton("Swap both assignment routes")
        self.swap_button.setObjectName("secondaryButton")
        self.copy_button.setToolTip(
            "Copy the donor route onto the target. If that route is only used "
            "once, use Swap instead so it is not deleted."
        )
        self.swap_button.setToolTip(
            "Stage both reciprocal route copies as one verified Undo action."
        )
        self.copy_button.clicked.connect(self._copy)
        self.swap_button.clicked.connect(self._swap)
        buttons.addWidget(self.copy_button)
        buttons.addWidget(self.swap_button)
        buttons.addStretch(1)
        grid.addLayout(buttons, 4, 0, 1, 2)
        root.addWidget(picker)

        staged_heading = QHBoxLayout()
        staged_heading.addWidget(QLabel("Staged assignment routes"))
        staged_heading.addStretch(1)
        self.revert_button = QPushButton("Revert selected")
        self.revert_button.setObjectName("dangerQuietButton")
        self.revert_button.clicked.connect(self._revert)
        staged_heading.addWidget(self.revert_button)
        root.addLayout(staged_heading)
        self.table = QTableWidget(0, 3)
        self.table.setObjectName("assetTable")
        self.table.setHorizontalHeaderLabels(("Target", "Donor", "Action"))
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.table.itemSelectionChanged.connect(self._update_buttons)
        root.addWidget(self.table, 1)
        self.status = QLabel("Load a game to choose stock plays.")
        self.status.setObjectName("mutedLabel")
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        self._update_buttons()

    def set_model(self, model: PagedModel | None) -> None:
        self._plays = (
            tuple(
                sorted(
                    (
                        (int(row.fields["index"]), row.title)
                        for row in model.rows
                        if row.kind == "play"
                    ),
                    key=lambda item: item[0],
                )
            )
            if model is not None
            else ()
        )
        for combo in (self.target_play, self.donor_play):
            previous = combo.currentData()
            combo.clear()
            for index, name in self._plays:
                combo.addItem(f"{index:03d} · {name}", index)
            restored = combo.findData(previous)
            if restored >= 0:
                combo.setCurrentIndex(restored)
        if len(self._plays) > 1 and self.donor_play.currentIndex() == 0:
            self.donor_play.setCurrentIndex(1)
        self.refresh()

    def _coordinates(self) -> tuple[int, int, int, int] | None:
        values = (
            self.target_play.currentData(),
            self.target_slot.currentData(),
            self.donor_play.currentData(),
            self.donor_slot.currentData(),
        )
        if any(type(value) is not int for value in values):
            return None
        return values  # type: ignore[return-value]

    def _copy(self) -> None:
        reason = str(self.copy_button.property("disableReason") or "").strip()
        if reason:
            QMessageBox.information(
                self,
                "Cannot copy route yet",
                reason
                + "\n\nStock copy only — not freehand. Load APF, pick different "
                "target/donor play·slot, then Copy.",
            )
            return
        coordinates = self._coordinates()
        if coordinates is None:
            return
        if coordinates[:2] == coordinates[2:]:
            QMessageBox.information(self, "Choose a donor", "Target and donor must differ.")
            return
        self.run_task(
            "Copying stock APF assignment route",
            lambda progress: self.facade.replace_play_assignment_route(
                *coordinates, progress=progress
            ),
            lambda _result: self._mutation_complete(
                "Stock assignment route staged and independently verified."
            ),
            True,
            show_errors=False,
            on_error=lambda message: self._copy_failed(coordinates, message),
        )

    def _copy_failed(self, coordinates, message: str) -> None:
        if message.strip() != ROUTE_ORPHAN_MESSAGE.strip():
            QMessageBox.critical(self, "Could not copy route", message)
            return
        self._offer_relay_copy(coordinates)

    def _offer_relay_copy(self, coordinates) -> None:
        candidates = tuple(
            self.facade.relay_play_assignment_route_candidates(*coordinates)
        )
        if not candidates:
            QMessageBox.warning(
                self,
                "No relay available",
                ROUTE_ORPHAN_MESSAGE
                + "\n\nNo other assignment shares a spare route that could "
                "carry the target's route, so use Swap instead.",
            )
            return
        relay = candidates[0]
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("Copy would delete a route")
        box.setText(ROUTE_ORPHAN_MESSAGE)
        box.setInformativeText(
            "You can copy through a relay instead: the donor route moves to "
            "the target, and the target's original route moves to a relay "
            "slot that already shares it. Nothing is deleted, and it stages "
            "as one Undo action."
        )
        relay_play, relay_slot = relay
        confirm = box.addButton(
            f"Copy via relay play {self._play_name(relay_play)} "
            f"(slot {relay_slot + 1})",
            QMessageBox.AcceptRole,
        )
        pick = box.addButton("Pick relay…", QMessageBox.ActionRole)
        box.addButton("Cancel", QMessageBox.RejectRole)
        box.exec_()
        clicked = box.clickedButton()
        if clicked is confirm:
            self._relay_copy(coordinates, relay)
        elif clicked is pick:
            self._pick_relay(coordinates, candidates)

    def _relay_label(self, relay) -> str:
        relay_play, relay_slot = relay
        return f"{self._play_name(relay_play)} · slot {relay_slot + 1}"

    def _pick_relay(self, coordinates, candidates) -> None:
        labels = [self._relay_label(relay) for relay in candidates]
        label, accepted = QInputDialog.getItem(
            self,
            "Pick a relay slot",
            "Relay assignment that will take the target's route:",
            labels,
            0,
            False,
        )
        if not accepted or label not in labels:
            return
        self._relay_copy(coordinates, candidates[labels.index(label)])

    def _relay_copy(self, coordinates, relay) -> None:
        relay_play, relay_slot = relay
        self.run_task(
            "Copying stock APF assignment route via relay",
            lambda progress: self.facade.copy_play_assignment_route_via_relay(
                *coordinates, relay_play, relay_slot, progress=progress
            ),
            lambda _result: self._mutation_complete(
                "Relayed route copy staged and independently verified."
            ),
            True,
        )

    def _swap(self) -> None:
        reason = str(self.swap_button.property("disableReason") or "").strip()
        if reason:
            QMessageBox.information(
                self,
                "Cannot swap routes yet",
                reason
                + "\n\nStock swap only — not freehand. Load APF, pick different "
                "target/donor, then Swap.",
            )
            return
        coordinates = self._coordinates()
        if coordinates is None:
            return
        if coordinates[:2] == coordinates[2:]:
            QMessageBox.information(self, "Choose two assignments", "The assignments must differ.")
            return
        self.run_task(
            "Swapping stock APF assignment routes",
            lambda progress: self.facade.swap_play_assignment_routes(
                *coordinates, progress=progress
            ),
            lambda _result: self._mutation_complete(
                "Both reciprocal routes were staged as one verified Undo action."
            ),
            True,
        )

    def _revert(self) -> None:
        reason = str(self.revert_button.property("disableReason") or "").strip()
        if reason:
            QMessageBox.information(
                self,
                "Nothing to revert",
                reason,
            )
            return
        selected = self.table.selectedItems()
        if not selected:
            return
        asset_id = selected[0].data(Qt.UserRole)
        if not isinstance(asset_id, str):
            return
        self.run_task(
            "Reverting APF assignment route",
            lambda progress: self.facade.revert(asset_id, progress),
            lambda _result: self._mutation_complete(
                "Assignment route reverted; a reciprocal swap partner was also "
                "reverted when chain safety required it."
            ),
            True,
        )

    def _play_name(self, index: int) -> str:
        return next((name for value, name in self._plays if value == index), f"Play {index}")

    def refresh(self) -> None:
        source_ready = bool(getattr(self.facade, "source_ready", False))
        session = getattr(self.facade, "session", None)
        modifications = getattr(session, "modifications", ()) if session else ()
        rows = [item for item in modifications if item.kind == PROVIDER_KIND]
        self.table.setRowCount(len(rows))
        for row_index, modification in enumerate(rows):
            metadata = modification.metadata
            target_play = int(metadata["target_play_index"])
            target_slot = int(metadata["target_slot_index"])
            donor_play = int(metadata["donor_play_index"])
            donor_slot = int(metadata["donor_slot_index"])
            values = (
                f"{self._play_name(target_play)} · slot {target_slot + 1}",
                f"{self._play_name(donor_play)} · slot {donor_slot + 1}",
                "Exact stock descriptor + chain",
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.UserRole, modification.asset_id)
                item.setForeground(QColor("#dce8f5"))
                item.setBackground(QColor("#0c1421"))
                self.table.setItem(row_index, column, item)
        self.status.setText(
            f"{len(rows)} route target{'s' if len(rows) != 1 else ''} staged. "
            "Build reparses the complete MASTER PLAY and preserves every chain start."
            if source_ready and self._plays
            else "Load a game to choose stock plays."
        )
        self._update_buttons()

    def _mutation_complete(self, message: str) -> None:
        self.status.setText(message)
        self.refresh()
        self.modifiedChanged.emit()

    def _update_buttons(self) -> None:
        ready = bool(self._plays) and bool(getattr(self.facade, "source_ready", False))
        coordinates = self._coordinates()
        differs = coordinates is not None and coordinates[:2] != coordinates[2:]
        # Never silent-gray: stay clickable; disableReason explains load/selection walls.
        if not getattr(self.facade, "source_ready", False):
            block = (
                "Load your APF game first. Stock assignment copy/swap needs MASTER "
                "PLAY data. Click still explains — buttons stay clickable."
            )
        elif not self._plays:
            block = (
                "No stock plays loaded yet. Load APF, wait for the play catalog, "
                "then pick target and donor."
            )
        elif not differs:
            block = (
                "Target and donor must be different play/slot pairs. Change one "
                "side, then Copy or Swap."
            )
        else:
            block = ""
        copy_tip = (
            block
            if block
            else (
                "Copy the donor route onto the target. If Copy says the route "
                "is only used once, use Swap."
            )
        )
        swap_tip = (
            block
            if block
            else "Stage both reciprocal route copies as one verified Undo action."
        )
        self.copy_button.setEnabled(True)
        self.swap_button.setEnabled(True)
        self.copy_button.setToolTip(copy_tip)
        self.swap_button.setToolTip(swap_tip)
        self.copy_button.setProperty("disableReason", block)
        self.swap_button.setProperty("disableReason", block)
        has_row = bool(self.table.selectedItems())
        revert_tip = (
            "Revert the selected staged assignment route from the project."
            if has_row
            else "Select a staged route row first, then Revert."
        )
        self.revert_button.setEnabled(True)
        self.revert_button.setToolTip(revert_tip)
        self.revert_button.setProperty(
            "disableReason", "" if has_row else revert_tip
        )


__all__ = ["PlayAssignmentRoutePanel"]
