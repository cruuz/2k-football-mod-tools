"""Saves & sliders panel for NFL 2K5 (settings block, resign, franchise year).

The panel exposes the A1+A4+A7 save trio natively: pick a SAVEGAME.DAT
(Settings1's 736-byte STG or Franchise1's 720,044-byte FXG), edit the 21
gameplay sliders, optionally advance the franchise year, and write a COPY of
the save plus a fresh 20-byte EXTRA signature derived from a user-owned
default.xbe.  The source save is never touched, and saves whose stored EXTRA
does not verify are refused upstream by the write-back route.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from PyQt5.QtCore import QObject, QRunnable, Qt, QThreadPool, pyqtSignal
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mod_editor.core.nfl2k5_save_writer import (
    FRANCHISE_DISPLAY_YEAR_BASE,
    SLIDER_LABELS,
    SLIDER_MODES,
    edit_save_file,
    read_save,
)


ProgressSink = Callable[[str, int, int], None]

SAVE_FILTER = "NFL 2K5 saves (SAVEGAME.DAT *.DAT);;All files (*)"
XBE_FILTER = "Xbox executables (default.xbe *.xbe);;All files (*)"


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


class SavePanel(QWidget):
    """Edit the 21 gameplay sliders and franchise year, then re-sign a copy."""

    error_raised = pyqtSignal(str)
    operation_state_changed = pyqtSignal(bool)

    def __init__(
        self,
        facade: Any | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.facade = facade
        self._busy = False
        self._tasks: set[_Task] = set()
        self._pool = QThreadPool(self)
        self._save_info: dict[str, object] | None = None
        self._slider_spins: dict[str, QDoubleSpinBox] = {}
        self.setObjectName("savePanel")
        self._build_ui()
        self._connect()
        self._refresh_controls()

    @property
    def operation_in_progress(self) -> bool:
        return self._busy

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 22)
        root.setSpacing(14)

        title = QLabel("Saves & Sliders (experimental)")
        title.setObjectName("bumpTitle")
        subtitle = QLabel(
            "Gameplay sliders (Settings1 and Franchise1 saves) plus the "
            "franchise year field, re-signed with the title-static key "
            "derived from your own default.xbe. Writes always go to a COPY: "
            "a mutated SAVEGAME.DAT and a fresh 20-byte EXTRA. Put both "
            "files back into the save container together."
        )
        subtitle.setObjectName("bumpMuted")
        subtitle.setWordWrap(True)
        root.addWidget(title)
        root.addWidget(subtitle)

        xbe_row = QHBoxLayout()
        xbe_row.addWidget(QLabel("Signing XBE"))
        self.xbe_field = QLineEdit()
        self.xbe_field.setReadOnly(True)
        self.xbe_field.setPlaceholderText(
            "Choose your default.xbe (needed to re-sign the save)"
        )
        xbe_row.addWidget(self.xbe_field, 1)
        self.xbe_button = QPushButton("Choose…")
        xbe_row.addWidget(self.xbe_button)
        root.addLayout(xbe_row)

        save_row = QHBoxLayout()
        save_row.addWidget(QLabel("Save file"))
        self.save_field = QLineEdit()
        self.save_field.setReadOnly(True)
        self.save_field.setPlaceholderText(
            "Choose a SAVEGAME.DAT (Settings1 or Franchise1)"
        )
        save_row.addWidget(self.save_field, 1)
        self.save_button = QPushButton("Choose…")
        save_row.addWidget(self.save_button)
        root.addLayout(save_row)

        table_card = QFrame()
        table_card.setObjectName("bumpCard")
        table_layout = QVBoxLayout(table_card)
        table_layout.setContentsMargins(0, 0, 0, 0)
        self.slider_table = QTableWidget(0, 4)
        self.slider_table.setHorizontalHeaderLabels(
            ("Slider", "Current", "Mirror", "New value")
        )
        self.slider_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.slider_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.slider_table.setAlternatingRowColors(True)
        self.slider_table.verticalHeader().setVisible(False)
        header = self.slider_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        table_layout.addWidget(self.slider_table, 1)
        root.addWidget(table_card, 1)

        options_row = QHBoxLayout()
        options_row.addWidget(QLabel("Slider write mode"))
        self.mode_combo = QComboBox()
        for mode in SLIDER_MODES:
            self.mode_combo.addItem(mode)
        self.mode_combo.setCurrentText("consistent")
        options_row.addWidget(self.mode_combo)
        options_row.addSpacing(18)
        options_row.addWidget(QLabel("Franchise year"))
        self.year_spin = QSpinBox()
        self.year_spin.setRange(FRANCHISE_DISPLAY_YEAR_BASE,
                                FRANCHISE_DISPLAY_YEAR_BASE + 60)
        self.year_spin.setEnabled(False)
        options_row.addWidget(self.year_spin)
        self.year_note = QLabel("")
        self.year_note.setObjectName("bumpMuted")
        options_row.addWidget(self.year_note, 1)
        root.addLayout(options_row)

        out_row = QHBoxLayout()
        out_row.addWidget(QLabel("Output save"))
        self.out_field = QLineEdit()
        self.out_field.setReadOnly(True)
        self.out_field.setPlaceholderText(
            "Choose where to write the mutated SAVEGAME.DAT copy"
        )
        out_row.addWidget(self.out_field, 1)
        self.out_button = QPushButton("Choose…")
        out_row.addWidget(self.out_button)
        root.addLayout(out_row)

        actions = QHBoxLayout()
        self.apply_button = QPushButton("Apply edits && re-sign copy")
        actions.addStretch(1)
        actions.addWidget(self.apply_button)
        root.addLayout(actions)

        progress_row = QHBoxLayout()
        self.progress_label = QLabel("")
        self.progress_label.setObjectName("bumpMuted")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.hide()
        progress_row.addWidget(self.progress_label, 1)
        progress_row.addWidget(self.progress_bar)
        root.addLayout(progress_row)

        self.status_label = QLabel(
            "Choose a default.xbe and a SAVEGAME.DAT to begin."
        )
        self.status_label.setObjectName("bumpMuted")
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)

    def _connect(self) -> None:
        self.xbe_button.clicked.connect(self._choose_xbe)
        self.save_button.clicked.connect(self._choose_save)
        self.out_button.clicked.connect(self._choose_out)
        self.apply_button.clicked.connect(self._apply_clicked)

    def _set_status(self, message: str) -> None:
        self.status_label.setText(message)

    def _refresh_controls(self) -> None:
        ready = not self._busy
        have_xbe = bool(self.xbe_field.text())
        have_save = self._save_info is not None
        have_out = bool(self.out_field.text())
        self.xbe_button.setEnabled(ready)
        self.save_button.setEnabled(ready)
        self.out_button.setEnabled(ready and have_save)
        self.slider_table.setEnabled(ready and have_save)
        self.mode_combo.setEnabled(ready and have_save)
        franchise = bool(have_save and self._save_info
                         and self._save_info.get("kind") == "franchise")
        self.year_spin.setEnabled(ready and franchise)
        self.apply_button.setEnabled(
            ready and have_xbe and have_save and have_out
        )

    def _run(
        self,
        operation: Callable[[ProgressSink], object],
        on_success: Callable[[object], None],
    ) -> None:
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
        self._set_status(f"Failed: {message}")
        self.error_raised.emit(message)
        QMessageBox.warning(self, "Saves & sliders", message)

    def _choose_xbe(self) -> None:
        chosen, _filter = QFileDialog.getOpenFileName(
            self, "Choose your default.xbe", str(Path.home()), XBE_FILTER,
        )
        if chosen:
            self.xbe_field.setText(chosen)
            self._refresh_controls()

    def _choose_save(self) -> None:
        chosen, _filter = QFileDialog.getOpenFileName(
            self, "Choose a SAVEGAME.DAT", str(Path.home()), SAVE_FILTER,
        )
        if not chosen:
            return
        path = Path(chosen)

        def done(result: object) -> None:
            assert isinstance(result, dict)
            self._save_info = result
            self.save_field.setText(str(path))
            self._populate_sliders(result)
            kind = result.get("kind")
            if kind == "franchise":
                franchise = result.get("franchise") or {}
                display_year = int(franchise.get("display_year",
                                                 FRANCHISE_DISPLAY_YEAR_BASE))
                self.year_spin.setValue(display_year)
                self.year_note.setText(
                    f"Current in-save year: {display_year} "
                    "(display = 2004 + year field)"
                )
            else:
                self.year_note.setText(
                    "Settings saves carry sliders only (no franchise year)."
                )
            suggested = path.with_name(f"{path.stem}_edited{path.suffix}")
            self.out_field.setText(str(suggested))
            self._set_status(
                f"{kind} save loaded: {len(result.get('sliders') or {})} "
                "sliders available."
            )

        self._run(lambda progress: read_save(path), done)

    def _populate_sliders(self, info: dict[str, object]) -> None:
        sliders = info.get("sliders") or {}
        self.slider_table.setRowCount(len(SLIDER_LABELS))
        self._slider_spins.clear()
        for row, label in enumerate(SLIDER_LABELS):
            values = sliders.get(label) or {}
            editable = values.get("editable")
            mirror = values.get("mirror")
            name_item = QTableWidgetItem(label)
            current_item = QTableWidgetItem(
                f"{float(editable):.2f}" if editable is not None else "—"
            )
            mirror_item = QTableWidgetItem(
                f"{float(mirror):.2f}" if mirror is not None else "—"
            )
            self.slider_table.setItem(row, 0, name_item)
            self.slider_table.setItem(row, 1, current_item)
            self.slider_table.setItem(row, 2, mirror_item)
            spin = QDoubleSpinBox()
            spin.setRange(0.0, 1.0)
            spin.setSingleStep(0.05)
            spin.setDecimals(2)
            if editable is not None:
                spin.setValue(float(editable))
            spin.valueChanged.connect(self._slider_changed)
            self._slider_spins[label] = spin
            self.slider_table.setCellWidget(row, 3, spin)

    def _slider_changed(self, _value: float) -> None:
        pass

    def _choose_out(self) -> None:
        chosen, _filter = QFileDialog.getSaveFileName(
            self, "Choose where to write the mutated copy",
            self.out_field.text() or "SAVEGAME_edited.DAT", SAVE_FILTER,
        )
        if chosen:
            self.out_field.setText(chosen)

    def _collect_slider_edits(self) -> dict[str, float]:
        assert self._save_info is not None
        sliders = self._save_info.get("sliders") or {}
        edits: dict[str, float] = {}
        for label, spin in self._slider_spins.items():
            values = sliders.get(label) or {}
            original = values.get("editable")
            if original is None:
                continue
            new_value = spin.value()
            if abs(new_value - float(original)) > 1e-9:
                edits[label] = new_value
        return edits

    def _apply_clicked(self) -> None:
        if self._save_info is None:
            return
        save_path = Path(str(self._save_info.get("path") or ""))
        xbe_path = Path(self.xbe_field.text())
        out_path = Path(self.out_field.text())
        edits = self._collect_slider_edits()
        franchise = self._save_info.get("kind") == "franchise"
        year: int | None = None
        if franchise:
            original_year = int(
                (self._save_info.get("franchise") or {}).get(
                    "display_year", FRANCHISE_DISPLAY_YEAR_BASE
                )
            )
            if self.year_spin.value() != original_year:
                year = self.year_spin.value()
        if not edits and year is None:
            QMessageBox.information(
                self, "Saves & sliders",
                "Nothing changed yet — adjust a slider or the franchise "
                "year first.",
            )
            return
        extra_path = out_path.with_name("EXTRA")
        overwrite = out_path.exists() or extra_path.exists()
        summary_bits = [f"{len(edits)} slider edit(s)"]
        if year is not None:
            summary_bits.append(f"franchise year -> {year}")
        confirmation = QMessageBox.question(
            self,
            "Write the edited save copy?",
            f"{', '.join(summary_bits)}\n\n"
            f"Source (untouched): {save_path}\n"
            f"Output save: {out_path}\n"
            f"Output signature: {extra_path}"
            + ("\n\nExisting output files will be REPLACED."
               if overwrite else "")
            + "\n\nPut both files back into the container together.",
            QMessageBox.Ok | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )
        if confirmation != QMessageBox.Ok:
            return
        mode = self.mode_combo.currentText()

        def write(progress: ProgressSink) -> dict[str, object]:
            progress("Editing and re-signing the save copy", 0, 0)
            return edit_save_file(
                save_path, out_path, extra_path, xbe_path=xbe_path,
                sliders=edits, slider_mode=mode, franchise_year=year,
                overwrite=overwrite,
            )

        def done(result: object) -> None:
            assert isinstance(result, dict)
            changes = result.get("slider_changes") or []
            year_change = result.get("franchise_year_change")
            lines = [
                f"Slider writes: {len(changes)} (mode: {mode})",
            ]
            if year_change:
                lines.append(
                    "Franchise year: "
                    f"{year_change['old_display_year']} -> "
                    f"{year_change['new_display_year']}"
                )
            lines.append(f"EXTRA signature: {result['extra']['mac']}")
            self._set_status(f"Wrote edited save copy to {out_path.name}.")
            QMessageBox.information(
                self,
                "Edited save copy written",
                f"{out_path}\n{extra_path}\n\n" + "\n".join(lines) +
                "\n\nBoth files must be returned to the container together; "
                "the game verifies the signature at load.",
            )

        self._run(write, done)


__all__ = ["SavePanel"]
