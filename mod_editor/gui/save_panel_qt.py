"""Saves & sliders panel for NFL 2K5 (settings block, resign, franchise year).

The panel exposes the A1+A4+A7 save trio natively: pick a SAVEGAME.DAT
(Settings1's 736-byte STG or Franchise1's 720,044-byte FXG), edit the 21
gameplay sliders, optionally advance the franchise year, and write a COPY of
the save plus a fresh 20-byte EXTRA signature derived from a user-owned
default.xbe.  The source save is never touched, and saves whose stored EXTRA
does not verify are refused upstream by the write-back route.

b780 b10-profile: the "Game defaults" block takes the chosen default.xbe's new
default Quarter Length, Sim. Quarter Length and Chop Block into the same copy,
for the settings that still hold the old retail value (a saved profile and every
franchise keep the settings they were saved with, so new defaults never reach
them by themselves).
"""

from __future__ import annotations

from mod_editor.gui.ux_text import failure_body

from collections.abc import Callable
from pathlib import Path
import shutil
import tempfile
from typing import Any
import weakref

from PyQt5.QtCore import QObject, QRunnable, Qt, QThreadPool, pyqtSignal
from mod_editor.gui.task_delivery import roomy_pool  # b780 CI: 8 MiB worker stacks (macOS)
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
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

from mod_editor.gui.task_delivery import bound
from mod_editor.core import nfl2k5_profile_defaults as profile_defaults
from mod_editor.core.nfl2k5_save_writer import (
    FRANCHISE_DISPLAY_YEAR_BASE,
    SLIDER_LABELS,
    SLIDER_MODES,
    edit_save_file,
    read_save,
)


ProgressSink = Callable[[str, int, int], None]

SAVE_FILTER = "NFL 2K5 saves (SAVEGAME.DAT *.DAT);;All files (*)"
XBE_FILTER = "Game disc or executable (*.iso *.xiso default.xbe *.xbe);;All files (*)"


def resolve_xbe(chosen: Path, scratch: Path) -> Path:
    """b780 b10-profile: the default.xbe to use for a chosen file.

    A default.xbe is used as it is. A game disc image gives up the default.xbe inside it, copied to ``scratch`` (read only
    from the disc), so the signed copy and the game's default settings both come from the disc the player actually plays."""
    with chosen.open("rb") as handle:
        if handle.read(4) == b"XBEH":
            return chosen
    from mod_editor.core import nfl2k5_espn25_rosters as disc_files
    try:
        data = disc_files.read_xbe(chosen)
    except (OSError, ValueError, EOFError) as exc:
        raise ValueError("this file is neither a default.xbe nor a game disc the Studio can read") from exc
    if data[:4] != b"XBEH":
        raise ValueError("the disc's default.xbe is not an Xbox executable")
    target = scratch / "default.xbe"
    target.write_bytes(data)
    return target


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
        self._pool = roomy_pool(QThreadPool(self))
        self._save_info: dict[str, object] | None = None
        self._slider_spins: dict[str, QDoubleSpinBox] = {}
        self._targets: dict[str, object] | None = None       # the chosen default.xbe's defaults (b780 b10-profile)
        self._default_report: dict[str, object] | None = None
        self._default_checks: dict[str, QCheckBox] = {}
        self._xbe_file: Path | None = None                    # the default.xbe itself (inside a disc: a private copy)
        self._scratch_dir: str | None = None
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

        title = QLabel("Xbox save: sliders & franchise year (experimental)")  # b780-uxfix: a QLabel shows && as two
        title.setObjectName("bumpTitle")
        subtitle = QLabel(
            "Open SAVEGAME.DAT and your game disc (or its default.xbe), then save a signed copy. "
            "Keep the new SAVEGAME.DAT and EXTRA together when putting the save back."
        )
        subtitle.setObjectName("bumpMuted")
        subtitle.setWordWrap(True)
        root.addWidget(title)
        root.addWidget(subtitle)

        xbe_row = QHBoxLayout()
        xbe_row.addWidget(QLabel("Game disc or executable"))
        self.xbe_field = QLineEdit()
        self.xbe_field.setReadOnly(True)
        self.xbe_field.setPlaceholderText(
            "Choose your game disc (.iso) or its default.xbe (needed to re-sign the save)"
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

        defaults_card = QFrame()
        defaults_card.setObjectName("bumpCard")
        defaults_layout = QVBoxLayout(defaults_card)
        defaults_layout.setContentsMargins(12, 10, 12, 10)
        defaults_title = QLabel("Game defaults: Quarter Length, Sim. Quarter Length and Chop Block")
        defaults_title.setObjectName("bumpTitle")
        defaults_layout.addWidget(defaults_title)
        defaults_note = QLabel(profile_defaults.HELP_TEXT)
        defaults_note.setObjectName("bumpMuted")
        defaults_note.setWordWrap(True)
        defaults_layout.addWidget(defaults_note)
        self.defaults_table = QTableWidget(0, 4)
        self.defaults_table.setObjectName("gameDefaultsTable")
        self.defaults_table.setAccessibleName("Game defaults in this save")
        self.defaults_table.setHorizontalHeaderLabels(
            ("Setting", "In this save", "This build starts at", "Use the build's")
        )
        self.defaults_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.defaults_table.setSelectionMode(QAbstractItemView.NoSelection)
        self.defaults_table.verticalHeader().setVisible(False)
        defaults_header = self.defaults_table.horizontalHeader()
        defaults_header.setSectionResizeMode(QHeaderView.ResizeToContents)
        defaults_header.setSectionResizeMode(0, QHeaderView.Stretch)
        self.defaults_table.setMaximumHeight(124)
        defaults_layout.addWidget(self.defaults_table)
        self.defaults_status = QLabel("Choose your game disc (or its default.xbe) and a save to compare their game settings.")
        self.defaults_status.setObjectName("bumpMuted")
        self.defaults_status.setWordWrap(True)
        defaults_layout.addWidget(self.defaults_status)
        root.addWidget(defaults_card)

        options_row = QHBoxLayout()
        options_row.addWidget(QLabel("Slider copies to update (advanced)"))
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
        out_row.addWidget(QLabel("Save the copy as"))
        self.out_field = QLineEdit()
        self.out_field.setReadOnly(True)
        self.out_field.setPlaceholderText(
            "Where the new SAVEGAME.DAT copy goes (the original is never written)"
        )
        out_row.addWidget(self.out_field, 1)
        self.out_button = QPushButton("Choose…")
        out_row.addWidget(self.out_button)
        root.addLayout(out_row)

        actions = QHBoxLayout()
        self.apply_button = QPushButton("Make a signed save copy…")
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
            "Choose your game disc (or its default.xbe) and a SAVEGAME.DAT to begin."
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
        have_xbe = self._xbe_file is not None          # a chosen disc counts once its default.xbe has been read
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
        task.signals.result.connect(bound(self, on_success))
        task.signals.error.connect(self._failed)

        def finished() -> None:
            self._tasks.discard(task)
            if self._busy:
                self._busy = False
                self.operation_state_changed.emit(False)
            self.progress_bar.hide()
            self._refresh_controls()

        task.signals.finished.connect(bound(self, finished))
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
        QMessageBox.warning(self, "Couldn't finish that", failure_body(message))

    def _choose_xbe(self) -> None:
        chosen, _filter = QFileDialog.getOpenFileName(
            self, "Choose your game disc or default.xbe", str(Path.home()), XBE_FILTER,
        )
        if chosen:
            self.xbe_field.setText(chosen)
            self._xbe_file = None
            self._targets = None
            self._refresh_controls()
            self._read_build_defaults(Path(chosen))

    def _scratch_path(self) -> Path:
        """A private folder for a default.xbe taken out of a disc; removed when the panel goes away."""
        if self._scratch_dir is None:
            self._scratch_dir = tempfile.mkdtemp(prefix="2k5-saves-")
            weakref.finalize(self, shutil.rmtree, self._scratch_dir, True)
        return Path(self._scratch_dir)

    def _read_build_defaults(self, chosen: Path) -> None:
        """b780 b10-profile: find the default.xbe (inside a disc if a disc was chosen) and what it starts a fresh profile with."""

        def work(progress: ProgressSink) -> dict[str, object]:
            progress("Reading the game's default.xbe", 0, 0)
            xbe = resolve_xbe(chosen, self._scratch_path())
            return {"xbe": str(xbe), "targets": profile_defaults.build_targets(xbe.read_bytes())}

        def done(result: object) -> None:
            assert isinstance(result, dict)
            self._xbe_file = Path(str(result["xbe"]))
            self._targets = result["targets"]
            self._refresh_defaults()

        self._run(work, done)

    def _refresh_defaults(self) -> None:
        """Fill the Game defaults table from the chosen save and the chosen default.xbe (both needed)."""
        self._default_checks.clear()
        self._default_report = None
        self.defaults_table.setRowCount(0)
        if self._save_info is None or self._targets is None:
            self.defaults_status.setText("Choose your game disc (or its default.xbe) and a save to compare their game settings.")
            return
        state = self._targets.get("state")
        if state not in ("applied", "retail"):
            self.defaults_status.setText(
                "This default.xbe is not a build the tool recognises, so its default game settings are unknown. "
                "Sliders and the franchise year still work."
            )
            return
        try:
            report = profile_defaults.plan(Path(str(self._save_info["path"])).read_bytes(), self._targets)
        except (OSError, ValueError) as exc:
            self.defaults_status.setText(f"Could not read this save's game settings: {exc}")
            return
        self._default_report = report
        self.defaults_table.setRowCount(len(report["rows"]))
        for row, entry in enumerate(report["rows"]):
            self.defaults_table.setItem(row, 0, QTableWidgetItem(f"{entry['label']} ({entry['where']})"))
            self.defaults_table.setItem(row, 1, QTableWidgetItem(entry["current_text"]))
            self.defaults_table.setItem(row, 2, QTableWidgetItem(entry["target_text"] or "unknown"))
            box = QCheckBox("change" if entry["action"] == "change" else "already" if entry["action"] == "same"
                            else "change anyway")
            box.setChecked(entry["action"] == "change")
            box.setEnabled(entry["action"] != "same" and entry["target"] is not None)
            box.setToolTip(entry["note"])
            box.setAccessibleName(f"Use the build's {entry['label']}")
            self._default_checks[entry["key"]] = box
            self.defaults_table.setCellWidget(row, 3, box)
        changing = [entry for entry in report["rows"] if entry["action"] == "change"]
        kept = [entry for entry in report["rows"] if entry["action"] == "kept"]
        if changing:
            self.defaults_status.setText(
                "This save still has the old defaults for " + ", ".join(entry["label"] for entry in changing)
                + ". They are ticked: write a signed copy to take this build's."
                + (" Settings you changed yourself (" + ", ".join(entry["label"] for entry in kept) + ") are left alone."
                   if kept else "")
            )
        elif kept:
            self.defaults_status.setText(
                "Nothing to take: the settings differing from this build were set by you ("
                + ", ".join(entry["label"] for entry in kept) + "). Tick one to replace it."
            )
        else:
            self.defaults_status.setText("This save already has this build's default game settings.")

    def _collect_option_edits(self) -> dict[str, int]:
        """The ticked Game defaults rows, as the values to write."""
        if self._default_report is None:
            return {}
        edits: dict[str, int] = {}
        for entry in self._default_report["rows"]:
            box = self._default_checks.get(entry["key"])
            if box is not None and box.isChecked() and box.isEnabled() and entry["target"] is not None \
                    and entry["target"] != entry["current"]:
                edits[entry["key"]] = int(entry["target"])
        return edits

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
            self._refresh_defaults()

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
        xbe_path = self._xbe_file or Path(self.xbe_field.text())
        out_path = Path(self.out_field.text())
        edits = self._collect_slider_edits()
        option_edits = self._collect_option_edits()
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
        if not edits and year is None and not option_edits:
            QMessageBox.information(
                self, "Saves & sliders",
                "Nothing changed yet. Adjust a slider, tick a game default "
                "or change the franchise year first.",
            )
            return
        extra_path = out_path.with_name("EXTRA")
        overwrite = out_path.exists() or extra_path.exists()
        summary_bits = [f"{len(edits)} slider edit(s)"]
        if option_edits:
            summary_bits.append("game defaults: " + ", ".join(
                f"{profile_defaults.BY_KEY[key].label} -> {profile_defaults.BY_KEY[key].show(value)}"
                for key, value in option_edits.items()))
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
                overwrite=overwrite, options=option_edits,
            )

        def done(result: object) -> None:
            assert isinstance(result, dict)
            changes = result.get("slider_changes") or []
            year_change = result.get("franchise_year_change")
            lines = [
                f"Slider writes: {len(changes)} (mode: {mode})",
            ]
            for change in result.get("option_changes") or []:
                option = profile_defaults.BY_KEY[change["key"]]
                lines.append(f"{option.label}: {option.show(change['before'])} -> {option.show(change['after'])}")
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
