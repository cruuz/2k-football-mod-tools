"""Qt editor for the exact packed-player surface in an APF roster save."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .save_roster_players import (
    FIELDS,
    FIELDS_BY_ID,
    PLAYER_TEXT_FIELDS_BY_ID,
    MembershipSwap,
    PlayerFieldEdit,
    PlayerTextEdit,
    SaveRosterDocument,
    SaveRosterPlayerError,
    SaveRosterWriteReceipt,
    inspect_save,
    write_new_save,
)


Progress = Callable[[str, int, int], None]
TaskRunner = Callable[
    [str, Callable[[Progress], object], Callable[[object], None] | None, bool], bool
]


class SaveRosterPlayersPanel(QWidget):
    """Expose every proved player field without widening raw-save authority."""

    def __init__(self, run_task: TaskRunner):
        super().__init__()
        self.run_task = run_task
        self.document: SaveRosterDocument | None = None
        self.staged_fields: dict[tuple[int, str], PlayerFieldEdit] = {}
        self.staged_text: dict[str, PlayerTextEdit] = {}
        self.staged_swaps: list[MembershipSwap] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)
        heading = QLabel("Save player editor")
        heading.setObjectName("panelTitle")
        note = QLabel(
            "Edit all exact packed player fields in a raw APF Roster.ROS or a "
            "hash-verified Xbox 360 STFS save: 31 base ratings, 77 boolean "
            "abilities, five motion/style fields, tier, number, mirrored position, "
            "depth, appearance/equipment, IDs, fixed-allocation identity text, and "
            "safe existing roster-slot swaps. Overall is display-only until its "
            "complete engine formula is proved."
        )
        note.setObjectName("mutedLabel")
        note.setWordWrap(True)
        layout.addWidget(heading)
        layout.addWidget(note)

        source_row = QHBoxLayout()
        self.choose_button = QPushButton("Choose APF roster save…")
        self.choose_button.setObjectName("secondaryButton")
        self.source_label = QLabel("No save loaded")
        self.source_label.setObjectName("mutedLabel")
        self.source_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        source_row.addWidget(self.choose_button)
        source_row.addWidget(self.source_label, 1)
        layout.addLayout(source_row)

        self.boundary = QLabel(
            "The source is always opened read-only. Output and its verification "
            "receipt are always new files."
        )
        self.boundary.setObjectName("mutedLabel")
        self.boundary.setWordWrap(True)
        layout.addWidget(self.boundary)

        body = QHBoxLayout()
        body.setSpacing(12)
        player_box = QFrame()
        player_box.setObjectName("panel")
        player_form = QFormLayout(player_box)
        player_form.setContentsMargins(12, 10, 12, 10)
        self.player_index = QSpinBox()
        self.player_index.setObjectName("savePlayerIndex")
        self.player_index.setRange(0, 2_253)
        self.player_name = QLabel("—")
        self.player_name.setObjectName("fieldLabel")
        self.player_name.setTextInteractionFlags(Qt.TextSelectableByMouse)
        player_form.addRow("Player index", self.player_index)
        player_form.addRow("Identity", self.player_name)

        self.field = QComboBox()
        self.field.setObjectName("savePackedPlayerField")
        for row in FIELDS:
            category = row.category.replace("_", " ").title()
            self.field.addItem(f"{category} · {row.label}", row.field_id)
        self.value_stack = QStackedWidget()
        self.value_number = QSpinBox()
        self.value_number.setObjectName("savePackedPlayerNumber")
        self.value_choice = QComboBox()
        self.value_choice.setObjectName("savePackedPlayerChoice")
        self.value_stack.addWidget(self.value_number)
        self.value_stack.addWidget(self.value_choice)
        self.current_value = QLabel("Source: —")
        self.current_value.setObjectName("mutedLabel")
        self.stage_field = QPushButton("Stage player field")
        self.stage_field.setObjectName("primaryButton")
        player_form.addRow("Field", self.field)
        player_form.addRow("New value", self.value_stack)
        player_form.addRow("", self.current_value)
        player_form.addRow("", self.stage_field)

        self.text_field = QComboBox()
        self.text_field.setObjectName("savePlayerTextField")
        for field_id in PLAYER_TEXT_FIELDS_BY_ID:
            self.text_field.addItem(field_id.replace("_", " ").title(), field_id)
        self.text_value = QLineEdit()
        self.text_value.setObjectName("savePlayerTextValue")
        self.text_limit = QLabel("Existing allocation: —")
        self.text_limit.setObjectName("mutedLabel")
        self.stage_text = QPushButton("Stage identity text")
        self.stage_text.setObjectName("primaryButton")
        player_form.addRow("Text field", self.text_field)
        player_form.addRow("Replacement", self.text_value)
        player_form.addRow("", self.text_limit)
        player_form.addRow("", self.stage_text)
        body.addWidget(player_box, 3)

        roster_box = QFrame()
        roster_box.setObjectName("panel")
        roster_layout = QVBoxLayout(roster_box)
        roster_layout.setContentsMargins(12, 10, 12, 10)
        roster_title = QLabel("Existing roster membership")
        roster_title.setObjectName("fieldLabel")
        roster_note = QLabel(
            "Swap two populated counted slots. Counts, capacity, global uniqueness, "
            "and the complete player-pointer multiset stay unchanged."
        )
        roster_note.setObjectName("mutedLabel")
        roster_note.setWordWrap(True)
        self.first_slot = QComboBox()
        self.first_slot.setObjectName("saveMembershipFirst")
        self.second_slot = QComboBox()
        self.second_slot.setObjectName("saveMembershipSecond")
        self.stage_swap = QPushButton("Stage slot swap")
        self.stage_swap.setObjectName("primaryButton")
        self.staged_list = QListWidget()
        self.staged_list.setObjectName("savePlayerStagedEdits")
        self.clear_staged = QPushButton("Clear staged edits")
        self.clear_staged.setObjectName("dangerQuietButton")
        self.write_button = QPushButton("Write new verified raw save…")
        self.write_button.setObjectName("buildButton")
        roster_layout.addWidget(roster_title)
        roster_layout.addWidget(roster_note)
        roster_layout.addWidget(self.first_slot)
        roster_layout.addWidget(self.second_slot)
        roster_layout.addWidget(self.stage_swap)
        roster_layout.addWidget(self.staged_list, 1)
        roster_layout.addWidget(self.clear_staged)
        roster_layout.addWidget(self.write_button)
        body.addWidget(roster_box, 2)
        layout.addLayout(body, 1)

        self.choose_button.clicked.connect(self._choose_save)
        self.player_index.valueChanged.connect(self._refresh_player)
        self.field.currentIndexChanged.connect(self._refresh_field)
        self.text_field.currentIndexChanged.connect(self._refresh_text)
        self.stage_field.clicked.connect(self._stage_field)
        self.stage_text.clicked.connect(self._stage_text)
        self.stage_swap.clicked.connect(self._stage_swap)
        self.clear_staged.clicked.connect(self._clear)
        self.write_button.clicked.connect(self._choose_output)
        self._update_enabled()

    def _choose_save(self) -> None:
        selected, _filter = QFileDialog.getOpenFileName(
            self,
            "Choose APF raw roster or Xbox 360 STFS save",
            str(Path.home()),
            "APF save files (*.ROS *.ros *.CON *.con *.sav *.dat);;All files (*)",
        )
        if selected:
            self.load_path(Path(selected))

    def load_path(self, path: Path) -> None:
        self.run_task(
            "Inspecting APF save players",
            lambda progress: self._inspect_operation(path, progress),
            self._loaded,
            True,
        )

    @staticmethod
    def _inspect_operation(path: Path, progress: Progress) -> SaveRosterDocument:
        progress("Reading roster save read-only", 0, 1)
        result = inspect_save(path)
        progress("Complete packed-player inventory ready", 1, 1)
        return result

    def _loaded(self, result: object) -> None:
        if not isinstance(result, SaveRosterDocument):
            raise SaveRosterPlayerError("save inspection returned an invalid document")
        self.document = result
        self._clear()
        self.source_label.setText(
            f"{result.source.name} · {result.file_size:,} bytes · "
            f"{result.source_sha256[:12]}…"
        )
        if result.signed_container:
            self.boundary.setText(
                f"Hash-verified {result.container_kind or 'STFS'} container; "
                f"{result.payload_path or 'Roster.ROS'} was extracted read-only. "
                "The editor writes a verified raw payload for external reinjection, "
                "rehashing, and resigning with the owner's save manager/keyvault."
            )
        else:
            self.boundary.setText(
                "Writable raw roster payload. The selected source remains unchanged; "
                "the editor creates a new payload and JSON verification receipt."
            )
        self.first_slot.clear()
        self.second_slot.clear()
        for row in result.memberships:
            label = (
                f"Team {row.team_index:02d} · slot {row.roster_slot:02d} · "
                f"player {row.player_index:04d}"
            )
            value = (row.team_index, row.roster_slot)
            self.first_slot.addItem(label, value)
            self.second_slot.addItem(label, value)
        if self.second_slot.count() > 1:
            self.second_slot.setCurrentIndex(1)
        self._refresh_player()
        self._update_enabled()

    def _selected_field(self):
        return FIELDS_BY_ID[str(self.field.currentData())]

    def _refresh_player(self) -> None:
        if self.document is None:
            self.player_name.setText("—")
            return
        player = self.player_index.value()
        names = self.document.player_text_values(player)
        title = f"{names['first_name']} {names['last_name']}".strip()
        self.player_name.setText(title or f"Unnamed player {player:04d}")
        self._refresh_field()
        self._refresh_text()

    def _refresh_field(self) -> None:
        if self.document is None or self.field.currentIndex() < 0:
            return
        field = self._selected_field()
        player = self.player_index.value()
        source = self.document.player_values(player)[field.field_id]
        staged = self.staged_fields.get((player, field.field_id))
        active = source if staged is None else staged.value
        allowed = field.authorable_values
        if allowed is not None:
            self.value_choice.clear()
            for value in sorted(allowed):
                label = field.choices.get(value, str(value)) if field.choices else str(value)
                self.value_choice.addItem(f"{value} — {label}", value)
            index = self.value_choice.findData(active)
            self.value_choice.setCurrentIndex(max(0, index))
            self.value_stack.setCurrentWidget(self.value_choice)
        else:
            self.value_number.setRange(field.minimum, field.maximum)
            self.value_number.setValue(max(field.minimum, min(active, field.maximum)))
            self.value_stack.setCurrentWidget(self.value_number)
        source_label = field.choices.get(source, str(source)) if field.choices else str(source)
        self.current_value.setText(f"Source: {source} · {source_label}")

    def _refresh_text(self) -> None:
        if self.document is None or self.text_field.currentIndex() < 0:
            return
        player = self.player_index.value()
        field_id = str(self.text_field.currentData())
        allocation = self.document.player_text_allocation(player, field_id)
        staged = self.staged_text.get(allocation.allocation_id)
        self.text_value.setText(allocation.text if staged is None else staged.text)
        self.text_limit.setText(
            f"Existing allocation: {allocation.maximum_utf16_units} UTF-16 "
            f"characters · {len(allocation.owners)} known alias owner"
            f"{'s' if len(allocation.owners) != 1 else ''}"
        )

    def _stage_field(self) -> None:
        if self.document is None:
            return
        player = self.player_index.value()
        field = self._selected_field()
        value = (
            int(self.value_choice.currentData())
            if self.value_stack.currentWidget() is self.value_choice
            else self.value_number.value()
        )
        try:
            value = field.validate(value)
        except SaveRosterPlayerError as exc:
            QMessageBox.information(self, "Field not staged", str(exc))
            return
        source = self.document.player_values(player)[field.field_id]
        key = (player, field.field_id)
        if value == source:
            self.staged_fields.pop(key, None)
        else:
            self.staged_fields[key] = PlayerFieldEdit(player, field.field_id, value)
        self._refresh_staged()

    def _stage_text(self) -> None:
        if self.document is None:
            return
        player = self.player_index.value()
        field_id = str(self.text_field.currentData())
        allocation = self.document.player_text_allocation(player, field_id)
        value = self.text_value.text()
        try:
            encoded = value.encode("utf-16-be", errors="strict")
            if "\0" in value or len(encoded) // 2 > allocation.maximum_utf16_units:
                raise ValueError
        except (UnicodeEncodeError, ValueError):
            QMessageBox.information(
                self,
                "Text not staged",
                f"Replacement must fit the existing "
                f"{allocation.maximum_utf16_units}-character UTF-16 allocation.",
            )
            return
        if value == allocation.text:
            self.staged_text.pop(allocation.allocation_id, None)
        else:
            self.staged_text[allocation.allocation_id] = PlayerTextEdit(
                player, field_id, value
            )
        self._refresh_staged()

    def _stage_swap(self) -> None:
        if self.document is None:
            return
        first = self.first_slot.currentData()
        second = self.second_slot.currentData()
        if first == second:
            QMessageBox.information(
                self, "Swap not staged", "Choose two different populated roster slots."
            )
            return
        used = {
            (row.first_team, row.first_slot)
            for row in self.staged_swaps
        } | {
            (row.second_team, row.second_slot)
            for row in self.staged_swaps
        }
        if first in used or second in used:
            QMessageBox.information(
                self, "Swap not staged", "One selected slot is already in a staged swap."
            )
            return
        self.staged_swaps.append(MembershipSwap(*first, *second))
        self._refresh_staged()

    def _clear(self) -> None:
        self.staged_fields.clear()
        self.staged_text.clear()
        self.staged_swaps.clear()
        self._refresh_staged()

    def _refresh_staged(self) -> None:
        self.staged_list.clear()
        for edit in sorted(self.staged_fields.values(), key=lambda row: (row.player_index, row.field_id)):
            self.staged_list.addItem(
                f"Player {edit.player_index:04d} · {FIELDS_BY_ID[edit.field_id].label} → {edit.value}"
            )
        for edit in self.staged_text.values():
            self.staged_list.addItem(
                f"Player {edit.player_index:04d} · {edit.field_id.replace('_', ' ')} → text replacement"
            )
        for edit in self.staged_swaps:
            self.staged_list.addItem(
                f"Swap team {edit.first_team:02d}/slot {edit.first_slot:02d} ↔ "
                f"team {edit.second_team:02d}/slot {edit.second_slot:02d}"
            )
        self._update_enabled()

    def _choose_output(self) -> None:
        document = self.document
        if document is None or not self.staged_list.count():
            return
        suggested = document.source.with_name(
            f"{document.source.stem}-players.ROS"
        )
        selected, _filter = QFileDialog.getSaveFileName(
            self,
            "Write new verified raw APF roster",
            str(suggested),
            "Raw APF roster payload (*.ROS);;All files (*)",
        )
        if not selected:
            return
        destination = Path(selected)
        self.run_task(
            "Writing verified APF save players",
            lambda progress: self._write_operation(document, destination, progress),
            self._write_complete,
            True,
        )

    def _write_operation(
        self, document: SaveRosterDocument, destination: Path, progress: Progress
    ) -> SaveRosterWriteReceipt:
        progress("Creating separate raw roster and receipt", 0, 2)
        receipt = write_new_save(
            document,
            destination,
            field_edits=tuple(self.staged_fields.values()),
            text_edits=tuple(self.staged_text.values()),
            membership_swaps=tuple(self.staged_swaps),
        )
        progress("Independent packed-byte verification passed", 2, 2)
        return receipt

    def _write_complete(self, result: object) -> None:
        if not isinstance(result, SaveRosterWriteReceipt):
            raise SaveRosterPlayerError("save writer returned an invalid receipt")
        handoff = (
            "\n\nReinject this raw Roster.ROS, rehash, and resign it with the "
            "owner's save manager before testing."
            if result.external_reinjection_required
            else ""
        )
        QMessageBox.information(
            self,
            "New raw roster verified",
            f"Saved: {result.output}\nReceipt: {result.manifest}\n\n"
            f"Verified {result.field_edit_count} packed fields, "
            f"{result.text_edit_count} text allocations, and "
            f"{result.membership_swap_count} membership swaps; "
            f"{result.changed_byte_count} bytes changed. Source unchanged."
            f"{handoff}",
        )

    def _update_enabled(self) -> None:
        loaded = self.document is not None
        for widget in (
            self.player_index,
            self.field,
            self.value_stack,
            self.stage_field,
            self.text_field,
            self.text_value,
            self.stage_text,
            self.first_slot,
            self.second_slot,
            self.stage_swap,
        ):
            widget.setEnabled(loaded)
        staged = bool(self.staged_fields or self.staged_text or self.staged_swaps)
        self.clear_staged.setEnabled(staged)
        self.write_button.setEnabled(loaded and staged)


__all__ = ["SaveRosterPlayersPanel"]
