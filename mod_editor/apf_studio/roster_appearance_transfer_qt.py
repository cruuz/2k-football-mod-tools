"""Review and apply current/staged custom-team appearances to a new roster save."""
from __future__ import annotations

from pathlib import Path

from PyQt5.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                            QFileDialog, QLabel, QPushButton, QVBoxLayout)

from .roster_appearance_transfer import (TransferReceipt, TransferSource,
    inspect_transfer_source, write_transfer)
from .save_appearance import SaveAppearanceServiceError
import apf_stfs_roster_rehash as rehash


class RosterAppearanceTransferDialog(QDialog):
    def __init__(self, current, staged, run_task, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Apply my custom team appearance to this roster save")
        self.resize(660, 480)
        self.current = current
        self.staged = {row.slot: row for row in staged}
        self.run_task = run_task
        self.document: TransferSource | None = None
        self.last_receipt: TransferReceipt | None = None
        layout = QVBoxLayout(self)
        note = QLabel("Apply the HOME/AWAY colours and helmet/crest codes currently shown in the editor. "
                      "Match by ROST slot 32–39, then review the destination team names below. "
                      "Each slot changes at most 112 bytes. Jersey/shoulder/pants codes and artwork "
                      "already in the destination remain; import artwork separately.")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.include_staged = QCheckBox("Also apply other staged user-team appearances")
        self.include_staged.setChecked(False)
        self.include_staged.setEnabled(any(slot != current.slot for slot in self.staged))
        self.include_staged.toggled.connect(self._review)
        layout.addWidget(self.include_staged)
        self.choose_button = QPushButton("Choose roster save…")
        self.choose_button.clicked.connect(self._choose_source)
        layout.addWidget(self.choose_button)
        self.source_label = QLabel("Choose raw Roster.ROS, an Xbox STFS package, or decrypted PS3 USERDATA / roster ZIP.")
        self.source_label.setWordWrap(True)
        layout.addWidget(self.source_label)
        self.targets = QLabel("")
        self.targets.setWordWrap(True)
        layout.addWidget(self.targets)
        self.output_kind = QComboBox()
        self.output_kind.addItem("New raw Xbox Roster.ROS", False)
        self.output_kind.currentIndexChanged.connect(self._review)
        layout.addWidget(self.output_kind)
        self.boundary = QLabel("")
        self.boundary.setWordWrap(True)
        layout.addWidget(self.boundary)
        self.write_button = QPushButton("Write new roster save and receipt…")
        self.write_button.clicked.connect(self._choose_output)
        self.write_button.setEnabled(False)
        layout.addWidget(self.write_button)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        layout.addStretch(1)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def replacements(self):
        values = dict(self.staged) if self.include_staged.isChecked() else {}
        values[self.current.slot] = self.current
        return tuple(values[slot] for slot in sorted(values))

    def _choose_source(self):
        chosen, _ = QFileDialog.getOpenFileName(self, "Choose destination roster save", str(Path.home()),
            "APF roster (USERDATA *.ROS *.ros *.zip *.sav *.dat);;All files (*)")
        if chosen:
            self.load_path(Path(chosen))

    def load_path(self, path: Path):
        # Failed loads must not leave a previous destination writable.
        self.document = None
        self.last_receipt = None
        self.write_button.setEnabled(False)
        self.targets.clear()
        self.status.clear()
        self.source_label.setText(f"Inspecting {path.name}…")
        self.run_task("Inspecting destination roster appearance",
                      lambda progress: inspect_transfer_source(path), self._loaded, True)

    def _loaded(self, result):
        if not isinstance(result, TransferSource):
            raise SaveAppearanceServiceError("Roster inspection did not return a valid destination")
        self.document = result
        self.source_label.setText(f"{result.source.name} · {result.kind.upper()} · {result.source_sha256[:12]}…")
        self.output_kind.blockSignals(True)
        self.output_kind.clear()
        self.output_kind.addItem("New raw Xbox Roster.ROS", False)
        if result.xenia_package_supported:
            self.output_kind.addItem(rehash.XENIA_ONLY, True)
        self.output_kind.blockSignals(False)
        self._review()

    def _review(self):
        document = self.document
        if document is None:
            return
        selected = {row.slot for row in self.replacements()}
        lines = []
        for row in document.slots:
            target = row.target
            if target.slot in selected:
                state = "occupied" if target.occupied else "empty"
                lines.append(f"Slot {target.slot} → user team {target.user_team_id}: {target.display_name} ({state})")
        self.targets.setText("Destination teams:\n" + "\n".join(lines))
        self.write_button.setEnabled(len(lines) == len(selected))
        if self.output_kind.currentData():
            text = (rehash.XENIA_ONLY + ". Active data/table hashes and metadata hash are rebuilt. "
                    "The original console signature is preserved, not renewed. The pinned Xenia reader "
                    "does not check it (PROVED from source); full loading is HYPOTHESIS and UNWITNESSED.")
        else:
            text = "Writes a new raw Xbox Roster.ROS and verified receipt. In-game appearance is UNWITNESSED."
            if document.kind == "stfs":
                text += " " + document.package_reason
            if document.kind == "ps3":
                text += (" Converts PS3 first, carrying all 40 teams' uniform selectors and palette colours. "
                         "The selected slots then receive your editor colours and helmet/crest codes. "
                         "Custom texture files require a separate import.")
        self.boundary.setText(text)

    def _choose_output(self):
        if self.document is None:
            return
        package = bool(self.output_kind.currentData())
        suffix = "-appearance-xenia.stfs" if package else "-appearance.Roster.ROS"
        chosen, _ = QFileDialog.getSaveFileName(self, "Write a new roster save", str(
            self.document.source.with_name(self.document.source.stem + suffix)),
            "STFS package (*.stfs);;All files (*)" if package else "Raw Xbox roster (*.ROS);;All files (*)")
        if chosen:
            self.write_to(Path(chosen))

    def write_to(self, output: Path):
        document = self.document
        if document is None:
            raise SaveAppearanceServiceError("Choose a roster save before writing")
        replacements = self.replacements()
        package = bool(self.output_kind.currentData())
        self.run_task("Applying custom-team appearance to a new roster save",
                      lambda progress: write_transfer(document, replacements, output, xenia_package=package),
                      self._written, True)

    def _written(self, result):
        if not isinstance(result, TransferReceipt):
            raise SaveAppearanceServiceError("Roster transfer returned an invalid receipt")
        self.last_receipt = result
        self.status.setText(f"Verified slots changed: {', '.join(map(str, result.changed_slots))}. "
                           f"{result.changed_byte_count} appearance bytes changed.\n"
                           f"Saved: {result.output}\nReceipt: {result.manifest}\n"
                           + (rehash.XENIA_ONLY + ". " if result.output_is_package else "")
                           + "Output reparsed successfully; in-game appearance remains UNWITNESSED.")


__all__ = ["RosterAppearanceTransferDialog"]
