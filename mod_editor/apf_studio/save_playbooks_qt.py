"""Qt workspace for per-team playbook assignments in an APF roster save."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .save_playbooks import (
    PlaybookEdit,
    SavePlaybookDocument,
    SavePlaybookError,
    SavePlaybookWriteReceipt,
    inspect_save,
    stage_edit,
    write_new_save,
)


Progress = Callable[[str, int, int], None]
TaskRunner = Callable[[str, Callable[[Progress], object], Callable[[object], None] | None, bool], bool]


class SavePlaybookAssignmentsPanel(QWidget):
    """Inspect 40 team slots and safely write staged O/D pointer changes."""

    def __init__(self, run_task: TaskRunner):
        super().__init__()
        self.run_task = run_task
        self.document: SavePlaybookDocument | None = None
        self.staged: dict[int, PlaybookEdit] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        heading = QLabel("Save playbook assignments")
        heading.setObjectName("panelTitle")
        explanation = QLabel(
            "Choose an APF roster save, select any of its 40 team slots, and assign "
            "one of the 36 existing offensive and 33 existing defensive books. "
            "This changes team assignments only—not formations, plays, or routes."
        )
        explanation.setObjectName("mutedLabel")
        explanation.setWordWrap(True)
        layout.addWidget(heading)
        layout.addWidget(explanation)

        source_row = QHBoxLayout()
        self.choose_button = QPushButton("Choose APF roster save…")
        self.choose_button.setObjectName("secondaryButton")
        self.choose_button.setAccessibleName("Choose APF roster save")
        self.source_label = QLabel("No save loaded")
        self.source_label.setObjectName("mutedLabel")
        self.source_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        source_row.addWidget(self.choose_button)
        source_row.addWidget(self.source_label, 1)
        layout.addLayout(source_row)

        self.boundary = QFrame()
        self.boundary.setObjectName("warningPanel")
        boundary_layout = QVBoxLayout(self.boundary)
        boundary_layout.setContentsMargins(12, 9, 12, 9)
        self.boundary_title = QLabel("Load a save to inspect assignments")
        self.boundary_title.setObjectName("fieldLabel")
        self.boundary_note = QLabel(
            "The source save is opened read-only. Every successful edit goes to a "
            "new destination with a separate verification receipt."
        )
        self.boundary_note.setObjectName("mutedLabel")
        self.boundary_note.setWordWrap(True)
        boundary_layout.addWidget(self.boundary_title)
        boundary_layout.addWidget(self.boundary_note)
        layout.addWidget(self.boundary)

        body = QHBoxLayout()
        body.setSpacing(12)
        team_box = QFrame()
        team_box.setObjectName("panel")
        team_layout = QVBoxLayout(team_box)
        team_layout.setContentsMargins(12, 10, 12, 10)
        team_title = QLabel("All 40 team slots")
        team_title.setObjectName("fieldLabel")
        self.team_list = QListWidget()
        self.team_list.setObjectName("savePlaybookTeams")
        self.team_list.setAccessibleName("APF save team slots")
        team_layout.addWidget(team_title)
        team_layout.addWidget(self.team_list, 1)
        body.addWidget(team_box, 2)

        editor = QFrame()
        editor.setObjectName("panel")
        editor_layout = QVBoxLayout(editor)
        editor_layout.setContentsMargins(14, 12, 14, 12)
        editor_layout.setSpacing(8)
        self.team_heading = QLabel("Select a team slot")
        self.team_heading.setObjectName("panelTitle")
        offense_label = QLabel("Offensive playbook")
        offense_label.setObjectName("fieldLabel")
        self.offense = QComboBox()
        self.offense.setObjectName("offensivePlaybook")
        self.offense.setAccessibleName("Offensive playbook")
        defense_label = QLabel("Defensive playbook")
        defense_label.setObjectName("fieldLabel")
        self.defense = QComboBox()
        self.defense.setObjectName("defensivePlaybook")
        self.defense.setAccessibleName("Defensive playbook")
        self.stage_button = QPushButton("Stage both assignments")
        self.stage_button.setObjectName("primaryButton")
        self.stage_button.setToolTip(
            "Stage the selected offensive and defensive book together for this team."
        )
        self.stage_count = QLabel("0 teams staged")
        self.stage_count.setObjectName("mutedLabel")
        self.write_button = QPushButton("Write new raw save…")
        self.write_button.setObjectName("buildButton")
        self.write_button.setToolTip(
            "Create a new raw roster payload plus an independently verified receipt."
        )
        output_note = QLabel(
            "The receipt proves that only the selected four-byte assignment fields "
            "changed. In-game behavior still requires reinjection and emulator/hardware testing."
        )
        output_note.setObjectName("mutedLabel")
        output_note.setWordWrap(True)
        editor_layout.addWidget(self.team_heading)
        editor_layout.addWidget(offense_label)
        editor_layout.addWidget(self.offense)
        editor_layout.addWidget(defense_label)
        editor_layout.addWidget(self.defense)
        editor_layout.addWidget(self.stage_button)
        editor_layout.addWidget(self.stage_count)
        editor_layout.addStretch(1)
        editor_layout.addWidget(self.write_button)
        editor_layout.addWidget(output_note)
        body.addWidget(editor, 3)
        layout.addLayout(body, 1)

        self.choose_button.clicked.connect(self._choose_save)
        self.team_list.currentRowChanged.connect(self._select_team)
        self.stage_button.clicked.connect(self._stage_selected)
        self.write_button.clicked.connect(self._write_new_save)
        self._update_enabled()

    def _choose_save(self) -> None:
        selected, _filter = QFileDialog.getOpenFileName(
            self,
            "Choose APF roster save or raw roster payload",
            str(Path.home()),
            "APF save files (*.ROS *.ros *.sav *.dat);;All files (*)",
        )
        if selected:
            self.load_path(Path(selected))

    def load_path(self, path: Path) -> None:
        self.run_task(
            "Inspecting APF save playbooks",
            lambda progress: self._inspect_operation(path, progress),
            self._loaded,
            True,
        )

    @staticmethod
    def _inspect_operation(path: Path, progress: Progress) -> SavePlaybookDocument:
        progress("Reading APF roster save read-only", 0, 1)
        document = inspect_save(path)
        progress("Save assignments ready", 1, 1)
        return document

    def _loaded(self, result: object) -> None:
        document = result
        if not isinstance(document, SavePlaybookDocument):
            raise SavePlaybookError("save inspection returned an invalid document")
        self.document = document
        self.staged.clear()
        self.source_label.setText(
            f"{document.source.name} · {document.file_size:,} bytes · "
            f"{document.source_sha256[:12]}…"
        )
        self.offense.clear()
        self.defense.clear()
        for book in document.offense:
            self.offense.addItem(book.label, book.playbook_id)
        for book in document.defense:
            self.defense.addItem(book.label, book.playbook_id)
        if document.signed_container:
            self.boundary_title.setText("Verified STFS source — raw handoff output")
        else:
            self.boundary_title.setText("Writable raw roster payload")
        self.boundary_note.setText(document.boundary_message)
        self._refresh_team_list(preserve=0)
        self._update_enabled()

    def _assignment(self, team_index: int) -> tuple[int, int]:
        assert self.document is not None
        staged = self.staged.get(team_index)
        if staged is not None:
            return staged.offensive_playbook_id, staged.defensive_playbook_id
        source = self.document.teams[team_index]
        return source.offensive_playbook_id, source.defensive_playbook_id

    def _book_name(self, playbook_id: int) -> str:
        assert self.document is not None
        return next(book.name for book in self.document.playbooks if book.playbook_id == playbook_id)

    def _refresh_team_list(self, *, preserve: int | None = None) -> None:
        if self.document is None:
            self.team_list.clear()
            return
        current = self.team_list.currentRow() if preserve is None else preserve
        self.team_list.blockSignals(True)
        self.team_list.clear()
        for team in self.document.teams:
            offense, defense = self._assignment(team.team_index)
            marker = "● " if team.team_index in self.staged else ""
            item = QListWidgetItem(
                f"{marker}{team.label}  ·  O {self._book_name(offense)}  ·  "
                f"D {self._book_name(defense)}"
            )
            item.setData(Qt.UserRole, team.team_index)
            self.team_list.addItem(item)
        self.team_list.blockSignals(False)
        if self.team_list.count():
            self.team_list.setCurrentRow(max(0, min(current, self.team_list.count() - 1)))
            self._select_team(self.team_list.currentRow())

    @staticmethod
    def _set_combo_id(combo: QComboBox, playbook_id: int) -> None:
        index = combo.findData(playbook_id)
        if index < 0:
            raise SavePlaybookError(f"playbook {playbook_id} is missing from its side")
        combo.setCurrentIndex(index)

    def _select_team(self, row: int) -> None:
        if self.document is None or row < 0 or row >= self.team_list.count():
            self.team_heading.setText("Select a team slot")
            self._update_enabled()
            return
        item = self.team_list.item(row)
        team_index = int(item.data(Qt.UserRole))
        offense, defense = self._assignment(team_index)
        self.team_heading.setText(f"Team slot {team_index:02d}")
        self._set_combo_id(self.offense, offense)
        self._set_combo_id(self.defense, defense)
        self._update_enabled()

    def _selected_team_index(self) -> int | None:
        item = self.team_list.currentItem()
        return None if item is None else int(item.data(Qt.UserRole))

    def _stage_selected(self) -> None:
        if self.document is None:
            return
        team_index = self._selected_team_index()
        if team_index is None:
            return
        try:
            edit = stage_edit(
                self.document,
                team_index,
                int(self.offense.currentData()),
                int(self.defense.currentData()),
            )
        except SavePlaybookError as exc:
            QMessageBox.information(self, "Assignment not staged", str(exc))
            return
        if edit is None:
            self.staged.pop(team_index, None)
        else:
            self.staged[team_index] = edit
        self._refresh_team_list(preserve=team_index)
        self._update_enabled()

    def _write_new_save(self) -> None:
        document = self.document
        if document is None or not self.staged:
            return
        suggested = document.source.with_name(
            f"{document.source.stem}-playbooks{document.source.suffix or '.ROS'}"
        )
        selected, _filter = QFileDialog.getSaveFileName(
            self,
            "Write new raw APF roster save",
            str(suggested),
            "Raw APF roster payload (*.ROS);;All files (*)",
        )
        if not selected:
            return
        destination = Path(selected)
        edits = tuple(self.staged[index] for index in sorted(self.staged))
        self.run_task(
            "Writing verified APF save assignments",
            lambda progress: self._write_operation(
                document, edits, destination, progress
            ),
            self._write_complete,
            True,
        )

    @staticmethod
    def _write_operation(
        document: SavePlaybookDocument,
        edits: tuple[PlaybookEdit, ...],
        destination: Path,
        progress: Progress,
    ) -> SavePlaybookWriteReceipt:
        progress("Creating a separate raw save", 0, 2)
        receipt = write_new_save(document, edits, destination)
        progress("Independent assignment-byte verification passed", 2, 2)
        return receipt

    def _write_complete(self, result: object) -> None:
        if not isinstance(result, SavePlaybookWriteReceipt):
            raise SavePlaybookError("save writer returned an invalid receipt")
        QMessageBox.information(
            self,
            "New raw save verified",
            f"Saved: {result.output}\nReceipt: {result.manifest}\n\n"
            f"Verified {result.assignment_field_count} assignment fields; "
            f"{result.changed_byte_count} individual bytes changed. The source "
            "save was not modified."
            + (
                " Reinject this raw Roster.ROS, rehash, and resign it with the "
                "owner's save manager before testing."
                if result.external_reinjection_required
                else ""
            ),
        )

    def _update_enabled(self) -> None:
        writable = bool(self.document is not None and self.document.write_supported)
        selected = self._selected_team_index() is not None
        self.offense.setEnabled(writable and selected)
        self.defense.setEnabled(writable and selected)
        self.stage_button.setEnabled(writable and selected)
        self.write_button.setEnabled(writable and bool(self.staged))
        count = len(self.staged)
        self.stage_count.setText(f"{count} team{'s' if count != 1 else ''} staged")


__all__ = ["SavePlaybookAssignmentsPanel"]
