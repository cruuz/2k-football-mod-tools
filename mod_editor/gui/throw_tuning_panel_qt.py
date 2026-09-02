"""Throw Distance & Pass Arc workspace (Sliders & Gameplay → Throw Distance & Arc).

Two sliders over the game's own arm-strength curve tables in ``default.xbe``:
the deep-ball ceiling (55 = retail .. 100 yards at 99 arm) and the pass arc
(how long deep balls hang).  The panel reads the tables from a default.xbe or a
disc image, previews the resulting per-arm ceiling / hang time / apex live, and
writes a patched COPY (never the source).  Output is xemu-only, exactly like
Bump strength: the RSA signature stays stale.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from PyQt5.QtCore import QObject, QRunnable, Qt, QThreadPool, pyqtSignal
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSlider,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mod_editor.core import nfl2k5_throw_tuning as tt

ProgressSink = Callable[[str, int, int], None]

SOURCE_FILTER = (
    "NFL 2K5 default.xbe or disc image (default.xbe *.xbe *.xiso *.iso *.img);;"
    "All files (*)"
)
XBE_FILTER = "Xbox executables (default.xbe *.xbe);;All files (*)"
IMAGE_FILTER = "Xbox disc images (*.xiso *.iso *.img);;All files (*)"


class _TaskSignals(QObject):
    result = pyqtSignal(object)
    error = pyqtSignal(str)
    progress = pyqtSignal(str, int, int)
    finished = pyqtSignal()


class _Task(QRunnable):
    def __init__(self, operation: Callable[[ProgressSink], object]) -> None:
        super().__init__()
        self.operation = operation
        self.signals = _TaskSignals()
        self.setAutoDelete(False)

    def run(self) -> None:
        try:
            result = self.operation(self.signals.progress.emit)
        except BaseException as exc:
            self.signals.error.emit(str(exc).strip() or exc.__class__.__name__)
        else:
            self.signals.result.emit(result)
        finally:
            self.signals.finished.emit()


class ThrowTuningPanel(QWidget):
    """Deep-ball ceiling and pass-arc sliders over the retail curve tables."""

    error_raised = pyqtSignal(str)
    operation_state_changed = pyqtSignal(bool)

    def __init__(self, facade: Any | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.facade = facade
        self._busy = False
        self._tasks: set[_Task] = set()
        self._pool = QThreadPool(self)
        self._report: dict[str, object] | None = None
        self._syncing = False
        self.setObjectName("throwTuningPanel")
        self._build_ui()
        self._connect()
        self._refresh_preview()
        self._refresh_controls()

    @property
    def operation_in_progress(self) -> bool:
        return self._busy

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 22)
        root.setSpacing(14)

        title = QLabel("Throw Distance & Pass Arc")
        title.setObjectName("throwTitle")
        subtitle = QLabel(
            "NFL 2K5 caps every throw at a distance that is a curve of the passer's "
            "arm strength (retail: 55 yards at 99 arm, and the ball never climbs "
            "higher on a longer throw). These two sliders re-shape the game's own "
            "curve tables in default.xbe: a higher ceiling scales the whole league "
            "so mid-tier arms gain a few yards and only elite arms reach the top; "
            "more arc makes deep balls hang and climb. The patched copy is "
            "xemu-only (its signature cannot be regenerated)."
        )
        subtitle.setObjectName("throwMuted")
        subtitle.setWordWrap(True)
        root.addWidget(title)
        root.addWidget(subtitle)

        source_row = QHBoxLayout()
        source_row.addWidget(QLabel("Source"))
        self.source_field = QLineEdit()
        self.source_field.setReadOnly(True)
        self.source_field.setPlaceholderText(
            "Choose a default.xbe or a disc image to read its throw tables (read-only)"
        )
        source_row.addWidget(self.source_field, 1)
        self.source_button = QPushButton("Choose…")
        source_row.addWidget(self.source_button)
        root.addLayout(source_row)

        self.source_status = QLabel("Choose a source to read its current throw tables.")
        self.source_status.setObjectName("throwMuted")
        self.source_status.setWordWrap(True)
        root.addWidget(self.source_status)

        root.addWidget(self._build_sliders())
        root.addWidget(self._build_preview(), 1)

        out_row = QHBoxLayout()
        out_row.addWidget(QLabel("Patched copy"))
        self.target_field = QLineEdit()
        self.target_field.setReadOnly(True)
        self.target_field.setPlaceholderText(
            "Choose where to save the patched COPY (a new file; the source is never written)"
        )
        out_row.addWidget(self.target_field, 1)
        self.target_button = QPushButton("Choose…")
        out_row.addWidget(self.target_button)
        root.addLayout(out_row)

        actions = QHBoxLayout()
        self.reset_button = QPushButton("Reset to retail")
        actions.addWidget(self.reset_button)
        actions.addStretch(1)
        self.write_button = QPushButton("Write patched copy")
        actions.addWidget(self.write_button)
        root.addLayout(actions)

        progress_row = QHBoxLayout()
        self.progress_label = QLabel("")
        self.progress_label.setObjectName("throwMuted")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.hide()
        progress_row.addWidget(self.progress_label, 1)
        progress_row.addWidget(self.progress_bar)
        root.addLayout(progress_row)

        self.status_label = QLabel("")
        self.status_label.setObjectName("throwMuted")
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)

    def _build_sliders(self) -> QGroupBox:
        box = QGroupBox("Sliders")
        layout = QVBoxLayout(box)

        ceiling_row = QHBoxLayout()
        ceiling_row.addWidget(QLabel("Deep-ball ceiling at 99 arm"))
        self.ceiling_slider = QSlider(Qt.Horizontal)
        self.ceiling_slider.setRange(int(tt.MIN_MAX_DEEP_YARDS), int(tt.MAX_MAX_DEEP_YARDS))
        self.ceiling_slider.setValue(int(tt.RETAIL_MAX_DEEP_YARDS))
        self.ceiling_slider.setTickPosition(QSlider.TicksBelow)
        self.ceiling_slider.setTickInterval(5)
        self.ceiling_slider.setAccessibleName("Deep-ball ceiling in yards")
        ceiling_row.addWidget(self.ceiling_slider, 1)
        self.ceiling_spin = QSpinBox()
        self.ceiling_spin.setRange(int(tt.MIN_MAX_DEEP_YARDS), int(tt.MAX_MAX_DEEP_YARDS))
        self.ceiling_spin.setValue(int(tt.RETAIL_MAX_DEEP_YARDS))
        self.ceiling_spin.setSuffix(" yd")
        ceiling_row.addWidget(self.ceiling_spin)
        layout.addLayout(ceiling_row)
        ceiling_note = QLabel(
            "55 is retail. The curve is re-spaced as a scale: at 80, a 70 arm throws "
            "41, an 85 arm 52, a 95 arm 66, a 99 arm 80 (retail 40 / 45 / 50 / 55)."
        )
        ceiling_note.setObjectName("throwMuted")
        ceiling_note.setWordWrap(True)
        layout.addWidget(ceiling_note)

        arc_row = QHBoxLayout()
        arc_row.addWidget(QLabel("Pass arc on deep balls"))
        self.arc_slider = QSlider(Qt.Horizontal)
        self.arc_slider.setRange(0, 100)
        self.arc_slider.setValue(0)
        self.arc_slider.setTickPosition(QSlider.TicksBelow)
        self.arc_slider.setTickInterval(10)
        self.arc_slider.setAccessibleName("Pass arc percentage")
        arc_row.addWidget(self.arc_slider, 1)
        self.arc_spin = QSpinBox()
        self.arc_spin.setRange(0, 100)
        self.arc_spin.setValue(0)
        self.arc_spin.setSuffix(" %")
        arc_row.addWidget(self.arc_spin)
        layout.addLayout(arc_row)
        arc_note = QLabel(
            "0 leaves the retail speed table alone (deep balls fly at 20 yd/s and hang "
            "about 2.75 s at 55 yards). Higher values slow the ball past the last "
            "25 yards of the ceiling so it hangs longer and climbs higher; 40 % at an "
            "80-yard ceiling is a 5.0 s, 33-yard-high bomb."
        )
        arc_note.setObjectName("throwMuted")
        arc_note.setWordWrap(True)
        layout.addWidget(arc_note)
        return box

    def _build_preview(self) -> QGroupBox:
        box = QGroupBox("What each arm rating gets (deep ball, forced lob)")
        layout = QVBoxLayout(box)
        self.preview_table = QTableWidget(0, 5)
        self.preview_table.setHorizontalHeaderLabels(
            ("Arm", "Retail ceiling", "New ceiling", "Hang time", "Apex height")
        )
        self.preview_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.preview_table.setSelectionMode(QAbstractItemView.NoSelection)
        self.preview_table.setAlternatingRowColors(True)
        self.preview_table.verticalHeader().setVisible(False)
        self.preview_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        # Seven arm rows plus the header; never make the modder scroll to see
        # what a 99 arm gets.
        self.preview_table.setFixedHeight(32 * (len(tt.PREVIEW_ARMS) + 1) + 12)
        layout.addWidget(self.preview_table)
        self.curves_label = QLabel("")
        self.curves_label.setObjectName("throwMuted")
        self.curves_label.setWordWrap(True)
        self.curves_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.curves_label)
        return box

    def _connect(self) -> None:
        self.source_button.clicked.connect(self._choose_source)
        self.target_button.clicked.connect(self._choose_target)
        self.reset_button.clicked.connect(self.reset_to_retail)
        self.write_button.clicked.connect(self._write)
        self.ceiling_slider.valueChanged.connect(self._ceiling_from_slider)
        self.ceiling_spin.valueChanged.connect(self._ceiling_from_spin)
        self.arc_slider.valueChanged.connect(self._arc_from_slider)
        self.arc_spin.valueChanged.connect(self._arc_from_spin)

    # ------------------------------------------------------------ settings
    def settings(self) -> tt.TuningSettings:
        return tt.TuningSettings(float(self.ceiling_spin.value()), self.arc_spin.value() / 100.0)

    def set_settings(self, settings: tt.TuningSettings) -> None:
        self._syncing = True
        try:
            self.ceiling_slider.setValue(int(round(settings.max_deep_yards)))
            self.ceiling_spin.setValue(int(round(settings.max_deep_yards)))
            self.arc_slider.setValue(int(round(settings.arc * 100)))
            self.arc_spin.setValue(int(round(settings.arc * 100)))
        finally:
            self._syncing = False
        self._refresh_preview()
        self._refresh_controls()

    def reset_to_retail(self) -> None:
        self.set_settings(tt.TuningSettings())

    def _ceiling_from_slider(self, value: int) -> None:
        if self._syncing:
            return
        self._syncing = True
        try:
            self.ceiling_spin.setValue(value)
        finally:
            self._syncing = False
        self._refresh_preview()
        self._refresh_controls()

    def _ceiling_from_spin(self, value: int) -> None:
        if self._syncing:
            return
        self._syncing = True
        try:
            self.ceiling_slider.setValue(value)
        finally:
            self._syncing = False
        self._refresh_preview()
        self._refresh_controls()

    def _arc_from_slider(self, value: int) -> None:
        if self._syncing:
            return
        self._syncing = True
        try:
            self.arc_spin.setValue(value)
        finally:
            self._syncing = False
        self._refresh_preview()
        self._refresh_controls()

    def _arc_from_spin(self, value: int) -> None:
        if self._syncing:
            return
        self._syncing = True
        try:
            self.arc_slider.setValue(value)
        finally:
            self._syncing = False
        self._refresh_preview()
        self._refresh_controls()

    # ------------------------------------------------------------- preview
    def preview_rows(self) -> tuple[tt.PreviewRow, ...]:
        return tt.preview(tt.curves_for(self.settings()))

    def _refresh_preview(self) -> None:
        retail = tt.preview({name: tt.CURVES[name].retail for name in tt.EDITABLE_CURVES})
        try:
            curves = tt.curves_for(self.settings())
        except tt.ThrowTuningError as exc:
            self.status_label.setText(str(exc))
            return
        rows = tt.preview(curves)
        self.preview_table.setRowCount(len(rows))
        for index, (before, after) in enumerate(zip(retail, rows)):
            cells = (
                f"{int(round(after.arm * 100))}",
                f"{before.deep_cap_yards:g} yd",
                f"{after.deep_cap_yards:g} yd",
                f"{after.hang_seconds:.2f} s",
                f"{after.apex_yards:.1f} yd",
            )
            for column, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignCenter)
                self.preview_table.setItem(index, column, item)
        self.curves_label.setText(
            "Tables written: "
            + "   ".join(
                f"{name} " + " ".join(f"{x:g}→{y:g}" for x, y in pairs)
                for name, pairs in curves.items()
            )
        )

    # -------------------------------------------------------------- source
    def _choose_source(self) -> None:
        chosen, _filter = QFileDialog.getOpenFileName(
            self, "Choose default.xbe or a disc image", str(Path.home()), SOURCE_FILTER,
        )
        if chosen:
            self.load_source(Path(chosen))

    def load_source(self, source: Path) -> None:
        """Read the curve tables from ``source`` in the background."""

        def done(result: object) -> None:
            assert isinstance(result, dict)
            self.apply_report(result)

        self._run(lambda progress: tt.read_any(source), done)

    def apply_report(self, report: dict[str, object]) -> None:
        """Populate the panel from a ``read_any`` report (also used by tests)."""

        self._report = report
        self.source_field.setText(str(report["path"]))
        settings = report["settings"]
        assert isinstance(settings, tt.TuningSettings)
        self.set_settings(settings)
        curves = report["curves"]
        assert isinstance(curves, dict)
        edited = [name for name in tt.EDITABLE_CURVES if not curves[name]["retail"]]
        container = "disc image" if report.get("container") == "xiso" else "default.xbe"
        retail = " (retail default.xbe by SHA-256)" if report.get("matches_retail_sha256") else ""
        state = ("retail throw tables" if not edited
                 else "already tuned: " + ", ".join(edited) + " edited")
        self.source_status.setText(
            f"Read the {container}{retail}: {state}. Current ceiling "
            f"{settings.max_deep_yards:g} yd, arc {int(round(settings.arc * 100))} %."
        )
        self._refresh_controls()

    def current_settings(self) -> tt.TuningSettings | None:
        if self._report is None:
            return None
        settings = self._report["settings"]
        return settings if isinstance(settings, tt.TuningSettings) else None

    def _choose_target(self) -> None:
        source = self.source_field.text()
        is_image = bool(source) and tt.is_disc_image(source)
        default_name = "ESPN NFL 2K5 (throw tuned).xiso.iso" if is_image else "default_throw_tuned.xbe"
        chosen, _filter = QFileDialog.getSaveFileName(
            self, "Choose where to save the patched copy", default_name,
            IMAGE_FILTER if is_image else XBE_FILTER,
        )
        if chosen:
            self.target_field.setText(chosen)
            self._refresh_controls()

    # --------------------------------------------------------------- write
    def has_changes(self) -> bool:
        current = self.current_settings()
        if current is None:
            return False
        try:
            wanted = tt.curves_for(self.settings())
        except tt.ThrowTuningError:
            return False
        curves = self._report["curves"] if self._report else {}
        return any(
            tuple(wanted[name]) != tuple(curves[name]["points"])  # type: ignore[index]
            for name in tt.EDITABLE_CURVES
        )

    def _write(self) -> None:
        source_text = self.source_field.text()
        target_text = self.target_field.text()
        if not source_text or not target_text or not self.has_changes():
            return
        source = Path(source_text)
        target = Path(target_text)
        settings = self.settings()
        overwrite = target.exists()
        is_image = tt.is_disc_image(source)
        top = self.preview_rows()[-1]
        confirmation = QMessageBox.question(
            self,
            "Write a patched copy?",
            f"Ceiling {settings.max_deep_yards:g} yd at 99 arm, arc {int(round(settings.arc * 100))} % "
            f"({top.hang_seconds:.1f} s hang, {top.apex_yards:.0f} yd apex on the longest ball)\n\n"
            f"Source (untouched): {source}\n"
            + (f"REPLACING existing copy: {target}" if overwrite else f"New copy: {target}")
            + ("\n\nThis copies the whole disc image, then patches default.xbe inside the copy."
               if is_image else "")
            + "\n\nThe copy is xemu-only: its RSA signature stays stale.",
            QMessageBox.Ok | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )
        if confirmation != QMessageBox.Ok:
            return

        def write(progress: ProgressSink) -> dict[str, object]:
            progress("Patching throw tables", 0, 0)
            return tt.write_copy(source, target, settings=settings, overwrite=overwrite, progress=progress)

        def done(result: object) -> None:
            assert isinstance(result, dict)
            changes = result.get("changes") or []
            summary = ", ".join(str(change["curve"]) for change in changes)
            self.status_label.setText(
                f"Patched copy written to {target.name}: {summary} "
                f"({result.get('changed_byte_count')} bytes changed, digest recomputed, "
                "read-back verified)."
            )
            QMessageBox.information(
                self,
                "Patched copy written",
                f"{target}\n\nTables rewritten: {summary}.\n\n"
                "Keep this xemu-only: the RSA signature cannot be regenerated, so real "
                "hardware will reject it.",
            )
            try:
                self.apply_report(tt.read_any(target))
            except tt.ThrowTuningError:
                pass

        self._run(write, done)

    # ------------------------------------------------------------ plumbing
    def _run(self, operation: Callable[[ProgressSink], object],
             on_success: Callable[[object], None]) -> None:
        if self._busy:
            return
        self._busy = True
        self.operation_state_changed.emit(True)
        self.progress_bar.setRange(0, 0)
        self.progress_bar.show()
        self._refresh_controls()
        task = _Task(operation)
        self._tasks.add(task)
        task.signals.progress.connect(self._progress)
        task.signals.result.connect(on_success)
        task.signals.error.connect(self._failed)

        def finished() -> None:
            self._tasks.discard(task)
            if self._busy:
                self._busy = False
                self.operation_state_changed.emit(False)
            self.progress_bar.hide()
            self.progress_label.setText("")
            self._refresh_controls()

        task.signals.finished.connect(finished)
        try:
            self._pool.start(task)
        except BaseException:
            self._tasks.discard(task)
            if self._busy:
                self._busy = False
                self.operation_state_changed.emit(False)
            self.progress_bar.hide()
            self._refresh_controls()
            raise

    def _progress(self, stage: str, completed: int, total: int) -> None:
        self.progress_label.setText(stage)
        if total > 0:
            self.progress_bar.setRange(0, total)
            self.progress_bar.setValue(max(0, min(total, completed)))
        else:
            self.progress_bar.setRange(0, 0)

    def _failed(self, message: str) -> None:
        self.status_label.setText(f"Failed: {message}")
        self.error_raised.emit(message)
        QMessageBox.warning(self, "Throw tuning", message)

    def _refresh_controls(self) -> None:
        ready = not self._busy
        have_source = bool(self.source_field.text()) and self._report is not None
        self.source_button.setEnabled(ready)
        self.target_button.setEnabled(ready and have_source)
        self.reset_button.setEnabled(ready)
        self.write_button.setEnabled(
            ready and have_source and bool(self.target_field.text()) and self.has_changes()
        )
        if have_source and not self.has_changes() and ready:
            self.write_button.setToolTip("The sliders match the source's current tables.")
        else:
            self.write_button.setToolTip("")


__all__ = ["ThrowTuningPanel"]
