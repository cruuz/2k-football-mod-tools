"""Custom-team HOME/AWAY palette and helmet/crest selector editor."""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Callable

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

_TOOLS = str(Path(__file__).resolve().parents[2] / "tools")
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)
import apf_custom_team_appearance_patch  # noqa: E402

from .save_appearance import (
    RawSaveAppearanceDocument,
    SaveAppearanceServiceError,
    SaveAppearanceWriteReceipt,
    StfsRosterExtractReceipt,
    extract_raw_save,
    inspect_save as inspect_raw_save,
    write_new_save as write_new_raw_save,
)


class _BankEditor(QWidget):
    def __init__(self, label: str):
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(8)
        note = QLabel(
            f"{label}: ten exact 32-bit ARGB palette entries. The final eight "
            "bytes of each 0x30 palette record are metadata and are preserved."
        )
        note.setObjectName("metadataText")
        note.setWordWrap(True)
        outer.addWidget(note)

        palette_grid = QGridLayout()
        palette_grid.setHorizontalSpacing(8)
        palette_grid.setVerticalSpacing(5)
        self.palette: list[QLineEdit] = []
        self.swatches: list[QLabel] = []
        for index in range(10):
            palette_grid.addWidget(QLabel(f"ARGB {index}"), index, 0)
            swatch = QLabel("  ")
            swatch.setFixedSize(28, 20)
            swatch.setFrameShape(QFrame.Box)
            editor = QLineEdit()
            editor.setMaxLength(8)
            editor.setPlaceholderText("FF004C54")
            editor.setAccessibleName(f"{label} ARGB palette index {index}")
            editor.textChanged.connect(
                lambda _text, row=index: self._update_swatch(row)
            )
            palette_grid.addWidget(swatch, index, 1)
            palette_grid.addWidget(editor, index, 2)
            self.swatches.append(swatch)
            self.palette.append(editor)
        outer.addLayout(palette_grid)

        selector_grid = QGridLayout()
        selector_grid.setHorizontalSpacing(7)
        selector_grid.setVerticalSpacing(5)
        selector_grid.addWidget(QLabel("Selector"), 0, 0)
        for column, text in enumerate(
            ("Asset", "Byte 1", "Byte 2", "Byte 3", "Byte 4", "Byte 5", "Byte 6", "Byte 7"),
            start=1,
        ):
            selector_grid.addWidget(QLabel(text), 0, column)
        self.helmet = self._selector_row(
            selector_grid,
            1,
            "Helmet",
            23,
            9,
            (
                "Helmet asset (proved)",
                "Shell palette index (proved)",
                "Opaque selector byte 2",
                "Opaque selector byte 3",
                "Opaque selector byte 4",
                "Opaque selector byte 5",
                "Opaque selector byte 6",
                "Opaque selector byte 7",
            ),
        )
        self.logo = self._selector_row(
            selector_grid,
            2,
            "Crest",
            117,
            255,
            (
                "Crest catalog asset (proved)",
                "Opaque selector byte 1",
                "Opaque selector byte 2",
                "Opaque selector byte 3",
                "Opaque selector byte 4",
                "Opaque selector byte 5",
                "Opaque selector byte 6",
                "Opaque selector byte 7",
            ),
        )
        selector_note = QLabel(
            "Only the asset bytes and helmet shell-color index have proved names. "
            "The remaining selector bytes are deliberately shown as opaque."
        )
        selector_note.setObjectName("findingText")
        selector_note.setWordWrap(True)
        outer.addLayout(selector_grid)
        outer.addWidget(selector_note)

    @staticmethod
    def _selector_row(
        grid: QGridLayout,
        row: int,
        label: str,
        maximum_asset: int,
        byte_one_maximum: int,
        tooltips: tuple[str, ...],
    ) -> list[QSpinBox]:
        grid.addWidget(QLabel(label), row, 0)
        fields: list[QSpinBox] = []
        for column in range(8):
            field = QSpinBox()
            field.setRange(
                0,
                maximum_asset
                if column == 0
                else byte_one_maximum
                if column == 1
                else 255,
            )
            field.setDisplayIntegerBase(16)
            field.setPrefix("0x")
            field.setToolTip(tooltips[column])
            field.setAccessibleName(f"{label} {tooltips[column]}")
            grid.addWidget(field, row, column + 1)
            fields.append(field)
        return fields

    def _update_swatch(self, index: int) -> None:
        text = self.palette[index].text().strip().upper()
        if len(text) == 8 and all(character in "0123456789ABCDEF" for character in text):
            self.swatches[index].setStyleSheet(
                f"background: #{text[2:]}; border: 1px solid #8795aa;"
            )
        else:
            self.swatches[index].setStyleSheet(
                "background: transparent; border: 1px solid #8795aa;"
            )

    def set_bank(self, bank: apf_custom_team_appearance_patch.AppearanceBank) -> None:
        for editor, color in zip(self.palette, bank.palette, strict=True):
            editor.setText(f"{color:08X}")
        for field, value in zip(self.helmet, bank.helmet_selector, strict=True):
            field.setValue(value)
        for field, value in zip(self.logo, bank.logo_selector, strict=True):
            field.setValue(value)

    def bank(self) -> apf_custom_team_appearance_patch.AppearanceBank:
        colors: list[int] = []
        for index, editor in enumerate(self.palette):
            text = editor.text().strip().upper()
            if len(text) != 8 or any(
                character not in "0123456789ABCDEF" for character in text
            ):
                raise ValueError(f"ARGB {index} must be exactly eight hexadecimal digits")
            colors.append(int(text, 16))
        return apf_custom_team_appearance_patch.AppearanceBank(
            tuple(colors),
            bytes(field.value() for field in self.helmet),
            bytes(field.value() for field in self.logo),
        )


class CustomTeamAppearancePanel(QFrame):
    """Dual-source bounded editor for safe custom slots 32 through 39."""

    modifiedChanged = pyqtSignal()

    def __init__(self, facade, run_task: Callable):
        super().__init__()
        self.facade = facade
        self.run_task = run_task
        self.setObjectName("panel")
        self._loaded = None
        self.raw_document: RawSaveAppearanceDocument | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 13, 14, 13)
        outer.setSpacing(9)
        title = QLabel("Custom Team Appearance · colors + helmet/crest selectors")
        title.setObjectName("panelTitle")
        description = QLabel(
            "Edit only the eight user-team slots. HOME and AWAY each own ten ARGB "
            "colors plus exact helmet and crest selector records. Stage stores only "
            "replacement JSON in the project; Build creates a new copied game and "
            "reopens the ROST to verify it. If you also build a Team Logo crest, that "
            "workflow composes package + logo cache + this appearance into one 0A."
            " Switch to Raw Roster Save after accepting a custom team to edit its "
            "save-local appearance records; save paths and bytes "
            "are never stored in the project."
        )
        description.setObjectName("cardBody")
        description.setWordWrap(True)
        outer.addWidget(title)
        outer.addWidget(description)

        source_kind_row = QHBoxLayout()
        source_kind_row.addWidget(QLabel("Appearance source:"))
        self.source_kind = QComboBox()
        self.source_kind.setAccessibleName("Custom team appearance source kind")
        self.source_kind.addItem("Game 0A · stage in project", "game")
        self.source_kind.addItem("Raw Roster Save · runtime user team", "raw_save")
        source_kind_row.addWidget(self.source_kind, 1)
        outer.addLayout(source_kind_row)

        self.raw_source = QFrame()
        self.raw_source.setObjectName("warningPanel")
        raw_layout = QVBoxLayout(self.raw_source)
        raw_layout.setContentsMargins(12, 9, 12, 9)
        raw_row = QHBoxLayout()
        self.choose_raw_button = QPushButton("Choose raw Roster.ROS…")
        self.choose_raw_button.setObjectName("secondaryButton")
        self.choose_raw_button.setAccessibleName("Choose raw APF Roster.ROS")
        self.raw_source_label = QLabel("No raw save loaded")
        self.raw_source_label.setObjectName("metadataText")
        self.extract_raw_button = QPushButton("Extract verified Roster.ROS…")
        self.extract_raw_button.setObjectName("secondaryButton")
        self.extract_raw_button.setAccessibleName(
            "Extract verified Roster.ROS from signed STFS package"
        )
        raw_row.addWidget(self.choose_raw_button)
        raw_row.addWidget(self.raw_source_label, 1)
        raw_row.addWidget(self.extract_raw_button)
        self.raw_boundary = QLabel(
            "The source is opened read-only. Output is always a separate raw save "
            "with an independent verification receipt."
        )
        self.raw_boundary.setObjectName("findingText")
        self.raw_boundary.setWordWrap(True)
        raw_layout.addLayout(raw_row)
        raw_layout.addWidget(self.raw_boundary)
        outer.addWidget(self.raw_source)
        self.choose_raw_button.clicked.connect(self._choose_raw_save)
        self.extract_raw_button.clicked.connect(self._extract_raw_save)

        slot_row = QHBoxLayout()
        slot_row.addWidget(QLabel("User team slot:"))
        self.slot = QComboBox()
        for slot in apf_custom_team_appearance_patch.USER_SLOTS:
            self.slot.addItem(f"Custom Team {slot} (slot {slot})", slot)
        self.slot.currentIndexChanged.connect(self._slot_changed)
        slot_row.addWidget(self.slot, 1)
        outer.addLayout(slot_row)

        self.banks = QTabWidget()
        self.home = _BankEditor("HOME")
        self.away = _BankEditor("AWAY")
        self.banks.addTab(self.home, "HOME")
        self.banks.addTab(self.away, "AWAY")
        outer.addWidget(self.banks)

        actions = QHBoxLayout()
        self.preset_button = QPushButton("Apply 2017 Eagles preset")
        self.preset_button.setObjectName("primaryButton")
        self.stage_button = QPushButton("Stage appearance")
        self.stage_button.setObjectName("secondaryButton")
        self.revert_button = QPushButton("Revert staged appearance")
        self.revert_button.setObjectName("dangerQuietButton")
        self.write_raw_button = QPushButton("Write verified raw save…")
        self.write_raw_button.setObjectName("buildButton")
        self.preset_button.clicked.connect(self._apply_preset)
        self.stage_button.clicked.connect(self._stage)
        self.revert_button.clicked.connect(self._revert)
        self.write_raw_button.clicked.connect(self._write_raw_save)
        actions.addWidget(self.preset_button)
        actions.addWidget(self.stage_button)
        actions.addWidget(self.revert_button)
        actions.addWidget(self.write_raw_button)
        actions.addStretch(1)
        outer.addLayout(actions)
        self.status = QLabel("Load your game to read the safe custom-team records.")
        self.status.setObjectName("metadataText")
        self.status.setWordWrap(True)
        outer.addWidget(self.status)
        self.source_kind.currentIndexChanged.connect(self._source_kind_changed)
        self.set_context()

    def _slot_value(self) -> int:
        return int(self.slot.currentData())

    def _raw_mode(self) -> bool:
        return self.source_kind.currentData() == "raw_save"

    def _populate_game_slots(self, preserve: int = 32) -> None:
        self.slot.blockSignals(True)
        self.slot.clear()
        for slot in apf_custom_team_appearance_patch.USER_SLOTS:
            self.slot.addItem(f"Custom Team {slot} (slot {slot})", slot)
        index = self.slot.findData(preserve)
        self.slot.setCurrentIndex(max(0, index))
        self.slot.blockSignals(False)

    def _populate_raw_slots(self, preserve: int = 32) -> None:
        self.slot.blockSignals(True)
        self.slot.clear()
        if self.raw_document is not None:
            for row in self.raw_document.slots:
                self.slot.addItem(row.label, row.slot)
        index = self.slot.findData(preserve)
        self.slot.setCurrentIndex(max(0, index))
        self.slot.blockSignals(False)

    def _appearance_from_controls(
        self,
    ) -> apf_custom_team_appearance_patch.CustomTeamAppearance:
        return apf_custom_team_appearance_patch.validate_appearance(
            apf_custom_team_appearance_patch.CustomTeamAppearance(
                self._slot_value(), self.home.bank(), self.away.bank()
            )
        )

    def set_context(self) -> None:
        raw_mode = self._raw_mode()
        self.raw_source.setVisible(raw_mode)
        self.stage_button.setVisible(not raw_mode)
        self.revert_button.setVisible(not raw_mode)
        self.write_raw_button.setVisible(raw_mode)
        if raw_mode:
            self._set_raw_context()
            return
        ready = bool(self.facade.source_ready)
        load_tip = (
            "Load your APF game first. Custom Team Appearance Stage needs a source. "
            "Click still explains — buttons stay clickable."
        )
        for widget in (
            self.slot,
            self.banks,
            self.preset_button,
        ):
            widget.setEnabled(ready)
        # Never silent-gray Stage/Revert/Write-raw
        self.stage_button.setEnabled(True)
        self.revert_button.setEnabled(True)
        project_write_tip = (
            "Write verified raw save is for raw Roster.ROS mode. "
            "In project mode use Stage appearance + Build instead."
        )
        self.write_raw_button.setEnabled(True)
        self.write_raw_button.setToolTip(project_write_tip)
        self.write_raw_button.setProperty("disableReason", project_write_tip)
        if not ready:
            self.stage_button.setToolTip(load_tip)
            self.stage_button.setProperty("disableReason", load_tip)
            self.revert_button.setToolTip(load_tip)
            self.revert_button.setProperty("disableReason", load_tip)
            self.status.setText("Load your game to read the safe custom-team records.")
            return
        try:
            appearance = self.facade.custom_team_appearance_value(self._slot_value())
        except Exception as exc:  # the shell reports source errors without crashing
            self.status.setText(f"Could not read this custom-team appearance: {exc}")
            return
        self._loaded = appearance
        self.home.set_bank(appearance.home)
        self.away.set_bank(appearance.away)
        target_id = apf_custom_team_appearance_patch.asset_id(appearance.slot)
        modified = target_id in self.facade.modified_asset_ids
        stage_tip = (
            "Stage HOME/AWAY appearance into the project. Build composes with names, "
            "ratings, and positions. Never mutates your original dump."
        )
        revert_tip = (
            "Remove the staged custom-team appearance from the project."
            if modified
            else "Nothing to revert—no staged appearance for this slot."
        )
        self.stage_button.setToolTip(stage_tip)
        self.stage_button.setProperty("disableReason", "")
        self.revert_button.setToolTip(revert_tip)
        self.revert_button.setProperty(
            "disableReason", "" if modified else revert_tip
        )
        self.status.setText(
            ("● Staged in this project. " if modified else "○ Source values (read-only). ")
            + "The normal Build path composes this safely with names, ratings, and positions."
        )

    def _set_raw_context(self) -> None:
        document = self.raw_document
        writable = bool(document is not None and document.write_supported and document.slots)
        for widget in (self.slot, self.banks, self.preset_button):
            widget.setEnabled(writable)
        # Never silent-gray: Stage/Revert in raw mode teach project-vs-raw walls.
        raw_stage_tip = (
            "Raw Roster.ROS mode uses Write verified raw save (or patched handoff), "
            "not project Stage. Switch to project Custom Team Appearance for Stage/Build."
        )
        self.stage_button.setEnabled(True)
        self.stage_button.setToolTip(raw_stage_tip)
        self.stage_button.setProperty("disableReason", raw_stage_tip)
        self.revert_button.setEnabled(True)
        self.revert_button.setToolTip(raw_stage_tip)
        self.revert_button.setProperty("disableReason", raw_stage_tip)
        write_tip = (
            "Write a verified private raw save copy (never mutates the opened file)."
            if writable
            else (
                "Choose a raw Roster.ROS after accepting/saving a custom team. "
                "New/Create Team is a scratch editor and is not the runtime proof route."
                if document is None
                else "This raw document has no writable user-team slots 32–39."
            )
        )
        self.write_raw_button.setEnabled(True)
        self.write_raw_button.setToolTip(write_tip)
        self.write_raw_button.setProperty(
            "disableReason", "" if writable else write_tip
        )
        self.extract_raw_button.setEnabled(
            bool(document is not None and document.signed_container)
        )
        if document is None:
            self.status.setText(
                "Choose a raw Roster.ROS after accepting/saving a custom team. "
                "New/Create Team is a scratch editor and is not the runtime proof route."
            )
            return
        self.raw_boundary.setText(document.boundary_message)
        if document.signed_container:
            self.write_raw_button.setText("Write patched raw handoff…")
        else:
            self.write_raw_button.setText("Write verified raw save…")
        slot = self._slot_value()
        row = next((item for item in document.slots if item.slot == slot), None)
        if row is None:
            self.status.setText("Choose one parsed user-team slot 32–39.")
            return
        self._loaded = row.appearance
        self.home.set_bank(row.appearance.home)
        self.away.set_bank(row.appearance.away)
        state = "occupied" if row.occupied else "currently empty"
        self.status.setText(
            f"{row.label} is {state}. Apply a preset or edit exact values, then "
            + (
                "write a patched raw handoff for external STFS reinjection. "
                if document.signed_container
                else "write a new raw save. "
            )
            + "The source and project remain unchanged."
        )

    def _source_kind_changed(self) -> None:
        preserve = self._slot_value() if self.slot.count() else 32
        if self._raw_mode():
            self._populate_raw_slots(preserve)
        else:
            self._populate_game_slots(preserve)
        self.set_context()

    def _choose_raw_save(self) -> None:
        selected, _filter = QFileDialog.getOpenFileName(
            self,
            "Choose raw APF Roster.ROS or STFS package",
            str(Path.home()),
            "APF save files (*.ROS *.ros *.sav *.dat);;All files (*)",
        )
        if selected:
            self.load_raw_path(Path(selected))

    def load_raw_path(self, path: Path) -> None:
        self.run_task(
            "Inspecting custom-team appearance save",
            lambda progress: self._inspect_raw_operation(path, progress),
            self._raw_loaded,
            True,
        )

    @staticmethod
    def _inspect_raw_operation(path: Path, progress):
        progress("Reading APF roster save read-only", 0, 1)
        document = inspect_raw_save(path)
        progress("Save-local custom-team appearances ready", 1, 1)
        return document

    def _raw_loaded(self, result: object) -> None:
        if not isinstance(result, RawSaveAppearanceDocument):
            raise SaveAppearanceServiceError("save inspection returned an invalid document")
        self.raw_document = result
        self.raw_source_label.setText(
            f"{result.source.name} · {result.file_size:,} bytes · "
            f"{result.source_sha256[:12]}…"
        )
        self._populate_raw_slots()
        self.set_context()

    def _slot_changed(self) -> None:
        self.set_context()

    def _extract_raw_save(self) -> None:
        document = self.raw_document
        if document is None or not document.signed_container:
            return
        suggested = document.source.with_name(
            f"{document.source.stem}-extracted-Roster.ROS"
        )
        selected, _filter = QFileDialog.getSaveFileName(
            self,
            "Extract verified raw APF Roster.ROS",
            str(suggested),
            "Raw APF roster payload (*.ROS);;All files (*)",
        )
        if not selected:
            return
        destination = Path(selected)
        self.run_task(
            "Extracting verified STFS Roster.ROS",
            lambda progress: self._extract_raw_operation(
                document, destination, progress
            ),
            self._raw_extract_complete,
            True,
        )

    @staticmethod
    def _extract_raw_operation(document, destination, progress):
        progress("Verifying the STFS hash tree", 0, 2)
        receipt = extract_raw_save(document, destination)
        progress("Extracted raw roster reopened and verified", 2, 2)
        return receipt

    def _raw_extract_complete(self, result: object) -> None:
        if not isinstance(result, StfsRosterExtractReceipt):
            raise SaveAppearanceServiceError("STFS extractor returned an invalid receipt")
        QMessageBox.information(
            self,
            "Raw Roster.ROS extracted and verified",
            f"Saved: {result.output}\nReceipt: {result.manifest}\n\n"
            f"Extracted {result.payload_path} after verifying the STFS metadata, "
            "hash-table chain, data blocks, and raw roster graph. This is a raw "
            "payload, not a signed container. Reinject it with your external save "
            "manager; Mod Studio did not rehash or resign the STFS package.",
        )

    def _apply_preset(self) -> None:
        try:
            current = self._appearance_from_controls()
            preset = apf_custom_team_appearance_patch.eagles_2017_preset(current)
        except Exception as exc:
            self.status.setText(str(exc))
            return
        self.home.set_bank(preset.home)
        self.away.set_bank(preset.away)
        self.status.setText(
            "2017 Eagles preset loaded into the controls: midnight-green shell, "
            "white/silver detail palette, crest catalog 30 with the Xenia-proved "
            "routing tail; helmet asset and opaque helmet tail preserved. "
            + (
                "Choose Write verified raw save to create the accepted-team candidate."
                if self._raw_mode()
                else "Choose Stage appearance to add it to the project."
            )
        )

    def _stage(self) -> None:
        reason = str(self.stage_button.property("disableReason") or "").strip()
        if reason:
            from PyQt5.QtWidgets import QMessageBox

            QMessageBox.information(
                self,
                "Cannot stage appearance yet",
                reason
                + "\n\nFix: File → Load game, edit HOME/AWAY, then Stage. "
                "Never mutates your original dump.",
            )
            return
        try:
            appearance = self._appearance_from_controls()
        except Exception as exc:
            self.status.setText(str(exc))
            return
        self.run_task(
            "Staging custom-team appearance",
            lambda progress: self.facade.replace_custom_team_appearance(
                appearance, progress
            ),
            lambda _result: self._mutation_complete(),
            True,
        )

    def _revert(self) -> None:
        reason = str(self.revert_button.property("disableReason") or "").strip()
        if reason:
            from PyQt5.QtWidgets import QMessageBox

            QMessageBox.information(
                self,
                "Nothing to revert",
                reason + "\n\nStage a custom-team appearance first.",
            )
            return
        target_id = apf_custom_team_appearance_patch.asset_id(self._slot_value())
        self.run_task(
            "Reverting custom-team appearance",
            lambda progress: self.facade.revert(target_id, progress),
            lambda _result: self._mutation_complete(),
            True,
        )

    def _write_raw_save(self) -> None:
        reason = str(self.write_raw_button.property("disableReason") or "").strip()
        if reason:
            from PyQt5.QtWidgets import QMessageBox

            QMessageBox.information(
                self,
                "Cannot write raw save yet",
                reason,
            )
            return
        document = self.raw_document
        if document is None or not document.write_supported:
            return
        try:
            appearance = self._appearance_from_controls()
        except Exception as exc:
            self.status.setText(str(exc))
            return
        suggested = document.source.with_name(
            (
                f"{document.source.stem}-appearance-Roster.ROS"
                if document.signed_container
                else f"{document.source.stem}-appearance{document.source.suffix or '.ROS'}"
            )
        )
        selected, _filter = QFileDialog.getSaveFileName(
            self,
            (
                "Write patched raw APF roster handoff"
                if document.signed_container
                else "Write verified raw APF roster save"
            ),
            str(suggested),
            "Raw APF roster payload (*.ROS);;All files (*)",
        )
        if not selected:
            return
        destination = Path(selected)
        self.run_task(
            "Writing verified custom-team appearance save",
            lambda progress: self._write_raw_operation(
                document, appearance, destination, progress
            ),
            self._raw_write_complete,
            True,
        )

    @staticmethod
    def _write_raw_operation(document, appearance, destination, progress):
        progress("Creating a separate raw save", 0, 2)
        receipt = write_new_raw_save(document, appearance, destination)
        progress("Independent appearance-byte verification passed", 2, 2)
        return receipt

    def _raw_write_complete(self, result: object) -> None:
        if not isinstance(result, SaveAppearanceWriteReceipt):
            raise SaveAppearanceServiceError("save writer returned an invalid receipt")
        QMessageBox.information(
            self,
            "New raw appearance save verified",
            f"Saved: {result.output}\nReceipt: {result.manifest}\n\n"
            f"Verified {result.edit_count} user-team appearance; "
            f"{result.changed_byte_count} individual bytes changed inside its "
            f"{result.authorized_byte_count}-byte union. The source and project "
            "were not modified. "
            + (
                "This output is a raw payload, not a signed STFS container. Reinject, "
                "rehash, and resign it with your external save manager."
                if result.external_reinjection_required
                else "Load this roster, then select/edit the accepted custom team "
                "in Quick Game or Edit Team Package."
            ),
        )

    def _mutation_complete(self) -> None:
        self.set_context()
        self.modifiedChanged.emit()


__all__ = ["CustomTeamAppearancePanel"]
