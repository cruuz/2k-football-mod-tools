"""Preview and export an older SOFTDRINK franchise upgrade as a signed copy."""
from pathlib import Path

from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QDialog, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QPlainTextEdit, QPushButton, QVBoxLayout,
)

from mod_editor.core import nfl2k5_franchise_upgrade_io as service

TITLE = "Upgrade franchise save to the current build"


class _Worker(QThread):
    succeeded = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, work, parent):
        super().__init__(parent)
        self.work = work

    def run(self):
        try:
            result = self.work()
        except Exception as exc:
            self.failed.emit(str(exc))
        else:
            self.succeeded.emit(result)


def preview_text(plan):
    receipt = plan.receipt
    lines = ["Preview complete. Your source save is unchanged."]
    for step in receipt["steps"]:
        if step["operation"] == "years":
            lines += [f"Season: {step['season']}",
                      f"Players with corrected experience: {step['changed_players']}",
                      f"Existing history entries shifted: {step['shifted_history_words']}",
                      f"Other player records preserved: {step['excluded_records']}"]
            changes = [c for c in step["changes"] if c["field"] == "years_pro"]
            lines += [f"  {c['player']}: {c['before']} → {c['after']} years" for c in changes[:12]]
            if len(changes) > 12:
                lines.append(f"  …and {len(changes) - 12} more in the receipt.")
        elif step["operation"] == "playbooks":
            lines.append(f"Current disc books verified: {len(step['teams'])} teams; {len(step['changes'])} fields changed")
        elif step["operation"] == "coach_sync":
            lines.append(f"Coach appearances: {len(step['changes'])} fields changed")
            lines += [f"  {c['coach']}: {c['field']} {c['before']} → {c['after']}" for c in step["changes"]]
        elif step["operation"] == "team_history":
            lines.append(f"Historical teams restored: {len(step['changes'])}; "
                         f"rows without historical evidence: {step['unresolved_rows']}")
    warnings = len(receipt["validation"]["after"]["findings"])
    lines += [f"Structural checks passed; {warnings} existing notices retained in the receipt.",
              f"Total changed fields: {receipt['changed_fields']}", "",
              "Write a signed copy to keep these changes. A JSON receipt beside the output folder records every field and both hashes.",
              "Your season progress, generated players, contracts and existing statistics are preserved."]
    return "\n".join(lines)


class FranchiseUpgradeDialog(QDialog):
    def __init__(self, source: Path, parent=None):
        super().__init__(parent)
        self.source = service.upgrade_source(Path(source))   # fx1: a loose SAVEGAME.DAT means its signed folder
        self.plan = None
        self.worker = None
        self.setWindowTitle(TITLE)
        self.resize(780, 580)
        layout = QVBoxLayout(self)
        hint = QLabel("For older SOFTDRINK franchises that began with the 2026 roster. "
                      "Choose the current build's disc to update experience, playbooks and coach appearances. "
                      "Preview first, then write a new signed save folder.")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        form = QFormLayout()
        source_label = QLabel(str(self.source))
        source_label.setWordWrap(True)
        form.addRow("Saved franchise", source_label)
        self.disc_edit = QLineEdit()
        self.disc_edit.setAccessibleName("Current build disc")
        self.disc_button = QPushButton("Choose disc…")
        row = QHBoxLayout()
        row.addWidget(self.disc_edit, 1)
        row.addWidget(self.disc_button)
        form.addRow("Current disc", row)
        self.output_edit = QLineEdit(str(self.source.with_name(self.source.stem + "-upgraded")))
        self.output_edit.setAccessibleName("New signed save folder")
        form.addRow("New save folder", self.output_edit)
        layout.addLayout(form)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setAccessibleName("Franchise upgrade preview")
        layout.addWidget(self.details, 1)
        row = QHBoxLayout()
        self.preview_button = QPushButton("Preview upgrade")
        self.write_button = QPushButton("Write signed copy")
        self.close_button = QPushButton("Close")
        self.write_button.setEnabled(False)
        row.addWidget(self.preview_button)
        row.addWidget(self.write_button)
        row.addStretch()
        row.addWidget(self.close_button)
        layout.addLayout(row)
        self.disc_button.clicked.connect(self._choose_disc)
        self.disc_edit.textChanged.connect(self._invalidate)
        self.preview_button.clicked.connect(self._preview)
        self.write_button.clicked.connect(self._write)
        self.close_button.clicked.connect(self.reject)

    def _invalidate(self):
        self.plan = None
        self.write_button.setEnabled(False)

    def _choose_disc(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose the current build disc", "", "Disc images (*.iso *.xiso);;All files (*)")
        if path:
            self.disc_edit.setText(path)

    def _busy(self, busy):
        for widget in (self.disc_edit, self.disc_button, self.output_edit, self.preview_button, self.close_button):
            widget.setEnabled(not busy)
        self.write_button.setEnabled(not busy and self.plan is not None)

    def _run(self, work, done):
        self._busy(True)
        self.worker = _Worker(work, self)
        self.worker.succeeded.connect(done)
        self.worker.failed.connect(self._failed)
        self.worker.finished.connect(lambda: self._busy(False))
        self.worker.start()

    def _failed(self, message):
        self.plan = None
        self.details.setPlainText("Upgrade refused: " + message)

    def _preview(self):
        self.plan = None
        self.details.setPlainText("Reading the signed save and current disc…")
        disc = Path(self.disc_edit.text().strip())
        self._run(lambda: service.plan_upgrade(self.source, disc), self._preview_ready)

    def _preview_ready(self, plan):
        self.plan = plan
        self.details.setPlainText(preview_text(plan))

    def _write(self):
        if self.plan is None:
            return
        text = self.output_edit.text().strip()
        output = Path(text) if text else None
        if output is None or not output.name:   # fx1: Path("").with_name raised inside this UI slot
            self.details.setPlainText("Choose a new save folder (a folder name next to the original save).")
            return
        receipt = output.with_name(output.name + ".upgrade.json")
        plan = self.plan
        self.details.setPlainText("Verifying the inputs and writing the signed copy…")
        def done(_result):
            self.plan = None
            self.details.setPlainText(f"Signed save written and verified:\n{output}\n\nField receipt:\n{receipt}")
        self._run(lambda: service.write_plan(plan, output, receipt), done)

    def reject(self):
        if self.worker is None or not self.worker.isRunning():
            super().reject()

    def closeEvent(self, event):
        if self.worker is not None and self.worker.isRunning():
            event.ignore()
        else:
            super().closeEvent(event)
