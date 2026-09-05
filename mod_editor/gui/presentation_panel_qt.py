"""Presentation workspace tab: the modern ESPN scorebug bar and ticker art, as a one-click copy.

Sits next to the Throw Distance & Arc tab in the Sliders & Gameplay workspace. It shows the
planned layout (mockup), reads whether a disc already carries the layout, and writes a copied
disc image with the mesh re-layout, the pinned bottom-centre placement, the repainted frame
atlas, ESPN strip and ticker atlas. Disc images only: the mesh lives in the field resource pack.
Everything stays xemu-only (RSA signature stale). The source is never modified.
"""

from __future__ import annotations

import importlib
import shutil
import sys
from collections.abc import Callable
from pathlib import Path

from PyQt5.QtCore import QObject, QRunnable, Qt, QThreadPool, pyqtSignal
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from mod_editor.core import nfl2k5_throw_tuning as tt
from mod_editor.gui.ux_text import XEMU_LINE, Details, plain_failure, show_operation_error, suggest_copy_name
from mod_editor.gui.task_delivery import bound

IMAGE_FILTER = "Disc images (*.iso *.xiso);;All files (*)"


def scorebug_layout_module():
    tools = Path(__file__).resolve().parents[2] / "tools"
    if str(tools) not in sys.path:
        sys.path.insert(0, str(tools))
    return importlib.import_module("nfl2k5_scorebug_layout")


class _Signals(QObject):
    finished = pyqtSignal(object)
    failed = pyqtSignal(str)


class _Task(QRunnable):
    def __init__(self, operation: Callable[[], object]) -> None:
        super().__init__()
        self.signals = _Signals()
        self._operation = operation

    def run(self) -> None:
        try:
            self.signals.finished.emit(self._operation())
        except Exception as exc:  # noqa: BLE001
            self.signals.failed.emit(f"{type(exc).__name__}: {exc}")


class PresentationPanel(QWidget):
    """ESPN scorebug bar + ticker art writer (disc images only)."""

    def __init__(self, facade: object | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._facade = facade
        self._pool = QThreadPool(self)
        self._task: _Task | None = None
        self._state = "n/a"
        self._target_generated = False
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        intro = QLabel(
            "Make a disc copy with a one-line ESPN score bar at the bottom of the screen. "
            "This page writes its own copy; it does not add a project edit. " + XEMU_LINE
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)
        intro_details = Details("Details")
        intro_details.add_text(
            "One horizontal ESPN-style bar at the bottom centre that never swaps sides: ESPN mark, away and "
            "home abbreviations and scores, down & distance, quarter, clock, play clock. Ticker art is "
            "repainted to a dark Bottom Line look. The original two-row bug, its side swap and the drop-box "
            "animations are replaced in place inside the field resource pack; nothing else on the disc changes.")
        layout.addWidget(intro_details)

        preview_box = QGroupBox("Scorebar preview (mockup)")
        preview_layout = QVBoxLayout(preview_box)
        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignCenter)
        self._show_mockup(None)
        preview_layout.addWidget(self.preview)
        layout.addWidget(preview_box)

        files = QGroupBox("Files")
        files_layout = QVBoxLayout(files)
        source_row = QHBoxLayout()
        source_row.addWidget(QLabel("Game disc (.iso)"))
        self.source_field = QLineEdit()
        self.source_field.setReadOnly(True)
        self.source_field.setPlaceholderText("Filled in when you open a disc (top right), or choose one here")
        source_row.addWidget(self.source_field, 1)
        self.source_button = QPushButton("Choose…")
        self.source_button.clicked.connect(self._choose_source)
        source_row.addWidget(self.source_button)
        files_layout.addLayout(source_row)
        self.source_status = QLabel("Open your game disc (top right) to see whether it already has the ESPN bar.")
        self.source_status.setWordWrap(True)
        files_layout.addWidget(self.source_status)
        target_row = QHBoxLayout()
        target_row.addWidget(QLabel("Save disc copy as"))
        self.target_field = QLineEdit()
        self.target_field.setPlaceholderText("Where the new disc goes (never the source)")
        target_row.addWidget(self.target_field, 1)
        self.target_button = QPushButton("Choose…")
        self.target_button.clicked.connect(self._choose_target)
        target_row.addWidget(self.target_button)
        self.target_field.textEdited.connect(lambda _t: self._user_target())
        self.target_field.textChanged.connect(lambda _t: self._refresh())
        files_layout.addLayout(target_row)
        layout.addWidget(files)

        actions = QHBoxLayout()
        self.write_button = QPushButton("Make disc with the ESPN bar")
        self.write_button.setEnabled(False)
        self.write_button.clicked.connect(self._write)
        actions.addWidget(self.write_button)
        actions.addStretch(1)
        layout.addLayout(actions)
        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        layout.addStretch(1)

    def _show_mockup(self, source: Path | None) -> None:
        """Draw the planned-look mockup, rendering it from ``source`` the first time.

        A release has no picture to ship (it is a render of retail geometry), so the panel
        used to show "mockup not shipped in this build" forever.  It is drawn from the user's
        own disc as soon as one is chosen, and cached beside the rest of the derived art.
        """

        mockup: Path | None = None
        try:
            from mod_editor.core import nfl2k5_scorebug_source_art as art

            mockup = art.preview_mockup(source)
        except Exception:  # noqa: BLE001 - the panel works without a picture
            mockup = None
        if mockup is not None and mockup.is_file():
            pix = QPixmap(str(mockup))
            # the mockup is a whole 640x480 frame; show the bottom quarter where the bar and ticker band live
            band = pix.copy(0, int(pix.height() * 0.78), pix.width(), int(pix.height() * 0.22))
            self.preview.setPixmap(band.scaledToWidth(1100, Qt.SmoothTransformation))
        else:
            self.preview.setText("Open your game disc to preview the layout.")

    # ------------------------------------------------------------------ state
    def load_source(self, path: Path | str) -> None:
        """Read the disc's scorebug state off the UI thread, then draw the preview (the open-disc hook)."""

        path = Path(path)
        if not tt.is_disc_image(path):
            self.apply_state(path, "n/a")
            return
        self.source_field.setText(str(path))
        self.source_status.setText("Reading disc…")
        self.preview.setText("Preparing preview…")
        module = scorebug_layout_module()

        def operation() -> object:
            return module.status(path)

        def done(state: object) -> None:
            if self.source_field.text() == str(path):
                self.apply_state(path, str(state))

        def failed(message: str) -> None:
            if self.source_field.text() == str(path):
                self.source_status.setText(plain_failure("read this disc", message))
                self.preview.setText("Open your game disc to preview the layout.")

        task = _Task(operation)
        task.signals.finished.connect(bound(self, done))
        task.signals.failed.connect(bound(self, failed))
        self._task = task
        self._pool.start(task)

    def _user_target(self) -> None:
        self._target_generated = False
        self._refresh()

    def apply_state(self, path: Path, state: str) -> None:
        """Populate from a known layout state (also used by tests)."""

        self._state = state
        self.source_field.setText(str(path))
        if state == "retail" and (not self.target_field.text().strip() or self._target_generated):
            self.target_field.setText(suggest_copy_name(path, suffix="ESPN scorebug"))
            self._target_generated = True
        text = {
            "retail": "Original scorebug: the ESPN bar can be written to a disc copy.",
            "applied": "Already installed: this disc carries the ESPN bar (mesh, placement, textures).",
            "foreign": "Not recognised: the scorebug bytes are neither retail nor this layout (changed by another tool), so nothing will be written.",
            "n/a": "Full disc required: this is not a disc image.",
        }[state]
        self.source_status.setText(text)
        if state in ("retail", "applied"):
            self._show_mockup(path)
        self._refresh()

    def _refresh(self) -> None:
        self.write_button.setEnabled(self._state == "retail" and bool(self.target_field.text()))

    def _choose_source(self) -> None:
        chosen, _f = QFileDialog.getOpenFileName(self, "Choose your game disc (.iso)", str(Path.home()), IMAGE_FILTER)
        if not chosen:
            return
        path = Path(chosen)
        if not tt.is_disc_image(path):
            self.apply_state(path, "n/a")
            return
        state = scorebug_layout_module().status(path)
        self.apply_state(path, state)

    def _choose_target(self) -> None:
        chosen, _f = QFileDialog.getSaveFileName(self, "Where should the new disc go?",
                                                 "ESPN NFL 2K5 (ESPN scorebug).xiso.iso", IMAGE_FILTER)
        if chosen:
            self.target_field.setText(chosen)
            self._target_generated = False
            self._refresh()

    # ------------------------------------------------------------------ write
    def _write(self) -> None:
        source = Path(self.source_field.text())
        target = Path(self.target_field.text())
        if not tt.is_disc_image(target):
            QMessageBox.warning(self, "Full disc required", "The copy must be a disc file (.iso). Fix: choose a name ending in .iso.")
            return
        if target.exists() and target.resolve() == source.resolve():
            QMessageBox.warning(self, "Same file", "Source and output are the same file. Fix: choose a different output file.")
            return
        answer = QMessageBox.question(
            self, "Make disc with the ESPN bar?",
            f"Source (unchanged): {source}\n"
            + (f"Replace existing disc copy: {target}" if target.exists() else f"New disc: {target}")
            + "\n\nThis copies the whole disc, then puts the one-line ESPN score bar (mesh, placement, "
              "textures) into the copy. Takes a few minutes.\n\n" + XEMU_LINE,
            QMessageBox.Ok | QMessageBox.Cancel, QMessageBox.Cancel)
        if answer != QMessageBox.Ok:
            return
        module = scorebug_layout_module()

        def operation() -> object:
            shutil.copyfile(source, target)
            return module.apply_in_place(target)

        self.write_button.setEnabled(False)
        self.status_label.setText("Copying the disc image and re-laying the scorebug…")
        task = _Task(operation)
        task.signals.finished.connect(self._done)
        task.signals.failed.connect(self._failed)
        self._task = task
        self._pool.start(task)

    def _done(self, receipt: object) -> None:
        assert isinstance(receipt, dict)
        target = Path(self.target_field.text())
        textures = ", ".join(receipt.get("textures") or []) or "none"
        self.status_label.setText(
            f"Written: {target.name}. Mesh refit {receipt.get('recompressed_bytes')}/4800 bytes, root at "
            f"{receipt.get('root')}, textures: {textures}. Read-back verified."
        )
        QMessageBox.information(self, "Disc ready",
                                f"{target}\n\nOpen it in xemu. " + XEMU_LINE)
        self.apply_state(target, "applied")

    def _failed(self, message: str) -> None:
        self.status_label.setText(plain_failure("make the disc", message))
        show_operation_error(self, "make the disc", message)
        self._refresh()


__all__ = ["PresentationPanel"]
