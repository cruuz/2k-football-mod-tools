"""Show the released-disc checker and a copyable support report inside Studio."""

from pathlib import Path
from threading import Event

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QDialog, QDialogButtonBox, QLabel, QPlainTextEdit, QProgressBar, QVBoxLayout

from mod_editor import __version__
from mod_editor.core import nfl2k5_disc_check
from mod_editor.gui.ux_text import plain_error


class _Cancelled(Exception):
    pass


def check_image(path: Path, progress, cancellation: Event) -> str | None:
    def advance(stage, done, total):
        if cancellation.is_set():
            raise _Cancelled
        progress(stage, done, total)

    try:
        advance("Reading the disc directory", 0, 0)
        result = nfl2k5_disc_check.check(path, progress=advance)
        explanation = nfl2k5_disc_check.describe(result)
        image = f"{path.name} ({result['image_size']:,} bytes)"
    except _Cancelled:
        return None
    except (OSError, ValueError) as exc:
        image = path.name
        explanation = f"Studio could not check this image. {plain_error(exc)}"
    if cancellation.is_set():
        return None
    return f"2K5 Mod Studio {__version__}\n{image}\n\n{explanation}"


class DiscCheckDialog(QDialog):
    def __init__(self, parent, path: Path):
        super().__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setWindowTitle("Check my SOFTDRINK disc")
        self.resize(540, 140)
        self.running = True
        self.close_studio_requested = False
        self.cancellation = Event()
        layout = QVBoxLayout(self)
        self.status = QLabel(f"Checking {path.name}")
        self.status.setTextFormat(Qt.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        layout.addWidget(self.progress)
        self.report = QPlainTextEdit()
        self.report.setReadOnly(True)
        self.report.setAccessibleName("Disc check report")
        self.report.hide()
        layout.addWidget(self.report, 1)
        buttons = QDialogButtonBox()
        self.copy_button = buttons.addButton("Copy report", QDialogButtonBox.ActionRole)
        self.copy_button.hide()
        self.copy_button.clicked.connect(self.copy_report)
        self.close_button = buttons.addButton("Cancel check", QDialogButtonBox.RejectRole)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def copy_report(self):
        QApplication.clipboard().setText(self.report.toPlainText())
        self.status.setText("Report copied to clipboard.")

    def update_progress(self, stage, done, total):
        if not self.running or self.cancellation.is_set():
            return
        self.status.setText(stage)
        if total > 0:
            self.progress.setRange(0, 1000)
            self.progress.setValue(min(1000, 1000 * done // total))

    def finish(self, report: str | None):
        self.running = False
        if report is None or self.cancellation.is_set():
            self.reject()
            return
        self.status.setText("Disc check result")
        self.progress.hide()
        self.report.setPlainText(report)
        self.report.show()
        self.copy_button.show()
        self.close_button.setText("Close")
        self.resize(max(560, self.width()), max(320, self.height()))

    def reject(self):
        if self.running:
            self.cancellation.set()
            self.status.setText("Stopping the disc check…")
            self.close_button.setEnabled(False)
            return
        super().reject()
