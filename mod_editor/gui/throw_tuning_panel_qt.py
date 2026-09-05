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
    QCheckBox,
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
from mod_editor.gui.ux_text import XEMU_LINE, Details, show_operation_error, source_captions, suggest_copy_name, write_caption
from mod_editor.gui.task_delivery import bound

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
            "Set throw distance and deep-ball flight. The original maximum at 99 Pass Arm "
            "Strength is 55 yards. The sliders re-shape the game's own curve tables in a copy; "
            "the source is never changed. " + XEMU_LINE
        )
        subtitle.setObjectName("throwMuted")
        subtitle.setWordWrap(True)
        root.addWidget(title)
        root.addWidget(subtitle)

        source_row = QHBoxLayout()
        self.source_caption = QLabel("Game disc (.iso)")
        source_row.addWidget(self.source_caption)
        self.source_field = QLineEdit()
        self.source_field.setReadOnly(True)
        self.source_field.setPlaceholderText(
            "Filled in when you open a disc (top right), or choose a disc / default.xbe here"
        )
        source_row.addWidget(self.source_field, 1)
        self.source_button = QPushButton("Choose…")
        source_row.addWidget(self.source_button)
        root.addLayout(source_row)

        self.source_status = QLabel("Open your game disc (top right), or choose a disc / default.xbe here, to read its throw tables.")
        self.source_status.setObjectName("throwMuted")
        self.source_status.setWordWrap(True)
        root.addWidget(self.source_status)

        root.addWidget(self._build_sliders())
        root.addWidget(self._build_preview(), 1)

        out_row = QHBoxLayout()
        self.target_caption = QLabel("Save disc copy as")
        out_row.addWidget(self.target_caption)
        self.target_field = QLineEdit()
        self.target_field.setReadOnly(True)
        self.target_field.setPlaceholderText(
            "Where the new copy goes (a new file; the source is never written)"
        )
        out_row.addWidget(self.target_field, 1)
        self.target_button = QPushButton("Choose…")
        out_row.addWidget(self.target_button)
        root.addLayout(out_row)

        actions = QHBoxLayout()
        self.reset_button = QPushButton("Reset to retail")
        actions.addWidget(self.reset_button)
        actions.addStretch(1)
        self.write_button = QPushButton("Make disc with these changes")
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
        ceiling_row.addWidget(QLabel("Longest throw at 99 Pass Arm Strength"))
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
            "55 is the original. The curve is re-spaced as a scale: at 80, a 70 arm throws "
            "41, an 85 arm 52, a 95 arm 66, a 99 arm 80 (original 40 / 45 / 50 / 55)."
        )
        ceiling_note.setObjectName("throwMuted")
        ceiling_note.setWordWrap(True)

        arc_row = QHBoxLayout()
        arc_row.addWidget(QLabel("Deep-ball arc"))
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
            "0 leaves the original speed table alone (deep balls fly at 20 yd/s and hang "
            "about 2.75 s at 55 yards). Higher values slow the ball past the last "
            "25 yards of the ceiling so it hangs longer and climbs higher; 40 % at an "
            "80-yard ceiling is a 5.0 s, 33-yard-high bomb. Realistic deep-ball flight overrides this arc."
        )
        arc_note.setObjectName("throwMuted")
        arc_note.setWordWrap(True)

        self.realistic_check = QCheckBox("Realistic deep-ball flight (recommended)")
        self.realistic_check.setToolTip(
            "Replaces the arc slider with the speed table elite NFL arms actually produce: "
            "~60 mph release, 3.2-3.9 s hang for 60-80 air yards, apex 13-20 yd. Short game stays retail."
        )
        layout.addWidget(self.realistic_check)
        self.arc_by_distance_check = QCheckBox("Arc by distance: 45-60 yd lobs hang high, 63+ yd keep the flat bomb")
        self.arc_by_distance_check.setToolTip(
            "Relocates the lob-speed table to an eight-point copy in the XBE header: every throw up to 40 "
            "yards keeps the retail speeds (short accuracy and power unchanged), 45 to 60 air yards get the "
            "high hanging arc (12 yd/s ground speed), 63 yards and beyond keep the realistic flat flight. "
            "The in-place table then only matters for read-back; the ceiling still applies."
        )
        layout.addWidget(self.arc_by_distance_check)
        realistic_note = QLabel(
            "Real deep balls are not moon balls: the longest tracked NFL completions (62-68 air yards) "
            "hang about 3.5 s with an apex near 15 yd. This table gives 55 yd → 2.8 s, 65 → 3.2 s, "
            "80 → 3.8 s (apex 19 yd)."
        )
        realistic_note.setObjectName("throwMuted")
        realistic_note.setWordWrap(True)
        self.notes_details = Details("Details")
        for note in (ceiling_note, arc_note, realistic_note):
            self.notes_details.content.addWidget(note)
        layout.addWidget(self.notes_details)

        # The same toggles ★ Build & Share carries, for a one-page copy.  Ticking them here does
        # not tick them on the Build tab (and the other way round): each page writes its own copy.
        self.also_details = Details("Also include (same changes as ★ Build & Share)")
        also_note = QLabel("These apply to the copy made on this page only; the Build tab keeps its own selection.")
        also_note.setObjectName("throwMuted")
        also_note.setWordWrap(True)
        self.also_details.content.addWidget(also_note)
        layout.addWidget(self.also_details)
        also = self.also_details.content

        self.catch_check = QCheckBox("Fix Catching && Interception sliders")
        self.catch_check.setToolTip(
            "Retail: the Catching slider barely reaches play. This 60-byte executable patch divides the "
            "catch roll by twice the receiver's side's slider: 50 = retail, 100 = double the catch odds, "
            "200 = quadruple. Raises both Catching menu ceilings to 200. xemu-only."
        )
        also.addWidget(self.catch_check)

        self.scorebug_check = QCheckBox("Modern ESPN scorebar (full disc required)")
        self.scorebug_check.setToolTip(
            "Re-lays the field scorebug mesh into one bar (ESPN mark, away/home abbreviations and scores, "
            "down & distance, quarter, clock, play clock), pins all three placement modes to the bottom centre "
            "above the ticker band, freezes the drop-box animations, and repaints the frame atlas and ESPN strip. "
            "Needs a disc image because the mesh lives in the field resource pack. xemu-only."
        )
        also.addWidget(self.scorebug_check)

        self.accel_check = QCheckBox("Gradual player acceleration")
        self.accel_check.setToolTip(
            "Retail has no acceleration: everyone is at top speed on the first step, so linemen keep pace with "
            "receivers at high Pursuit and slow quarterbacks burst out of the pocket. This executable patch ramps the "
            "per-frame speed cache from 60 % to 100 % of the rating: ~1 s at 99 agility, ~1.75 s at 50, ~2 s at 30; "
            "standing still resets it. xemu-only."
        )
        also.addWidget(self.accel_check)

        self.draft_check = QCheckBox("Smarter Franchise drafts && free agency")
        self.draft_check.setToolTip(
            "Retail CPU teams draft the best raw overall at their neediest positions (so the positions whose rookies "
            "roll the highest overalls flood round 1) and chase free agents in position-enum order. This executable "
            "patch picks by each prospect's edge over his own position's class, real positional value, the team's "
            "need order and a little noise, and scores free-agent targets the same way. Fantasy draft untouched. xemu-only."
        )
        also.addWidget(self.draft_check)

        self.returner_check = QCheckBox("Fix CPU kick && punt returners")
        self.returner_check.setToolTip(
            "The franchise auto depth chart never records which player had the best punt-return score: it stores the "
            "score itself as the roster slot, so the punt returner is whoever sits in slot 0 (often a QB), and the second "
            "kick returner is picked with a stale score. This executable patch tracks the players, scans the whole "
            "roster, keeps starters out unless nobody else is eligible, and limits returners to WR/CB/S/RB/FB. xemu-only."
        )
        also.addWidget(self.returner_check)

        self.progression_check = QCheckBox("Change player growth && decline")
        self.progression_check.setToolTip(
            "Retail development is a hidden archetype per player driving flat curves (+2 or +3 from rookie year to the "
            "prime). This data patch reshapes the ten aging-curve tables (growth over years 1-5 by rating family, "
            "steeper decline after year 9-12, speed first) and widens the archetype mix per position so more prospects "
            "become stars or busts. Draft-day ratings are unchanged. xemu-only."
        )
        also.addWidget(self.progression_check)

        self.edge_check = QCheckBox("Call defensive ends EDGE")
        self.edge_check.setToolTip(
            "Repoints the five position-abbreviation tables and the play-call Package legend to a new EDGE string "
            "hosted in the XBE header, shrinks the 18 'Defensive End(s)' long names to 'Edge Rusher(s)' in place, "
            "relabels the LDE/RDE formation slots EDGE (LEFT/RIGHT EDGE RUSHER), and on a disc image renames the 247 "
            "historic-team 'Def End' players to 'Edge' and two trivia questions. Pattern-checked, digests recomputed. xemu-only."
        )
        also.addWidget(self.edge_check)
        return box

    @staticmethod
    def _scorebug_module():
        """The layout tool lives in tools/ (it shares the disc-resource codecs there)."""

        import importlib
        import sys

        tools = Path(__file__).resolve().parents[2] / "tools"
        if str(tools) not in sys.path:
            sys.path.insert(0, str(tools))
        return importlib.import_module("nfl2k5_scorebug_layout")

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
        self.realistic_check.toggled.connect(self._option_toggled)
        self.arc_by_distance_check.toggled.connect(self._option_toggled)
        self.catch_check.toggled.connect(self._option_toggled)
        self.scorebug_check.toggled.connect(self._option_toggled)
        self.accel_check.toggled.connect(self._option_toggled)
        self.draft_check.toggled.connect(self._option_toggled)
        self.returner_check.toggled.connect(self._option_toggled)
        self.progression_check.toggled.connect(self._option_toggled)
        self.edge_check.toggled.connect(self._option_toggled)

    # ------------------------------------------------------------ settings
    def settings(self) -> tt.TuningSettings:
        return tt.TuningSettings(float(self.ceiling_spin.value()), self.arc_spin.value() / 100.0,
                                 self.realistic_check.isChecked(), self.arc_by_distance_check.isChecked())

    def catch_slider_requested(self) -> bool:
        return self.catch_check.isChecked()

    def _option_toggled(self, _checked: bool) -> None:
        if self._syncing:
            return
        self.arc_slider.setEnabled(not self.realistic_check.isChecked())
        self.arc_spin.setEnabled(not self.realistic_check.isChecked())
        self._refresh_preview()
        self._refresh_controls()

    def set_settings(self, settings: tt.TuningSettings) -> None:
        self._syncing = True
        try:
            self.ceiling_slider.setValue(int(round(settings.max_deep_yards)))
            self.ceiling_spin.setValue(int(round(settings.max_deep_yards)))
            self.arc_slider.setValue(int(round(settings.arc * 100)))
            self.arc_spin.setValue(int(round(settings.arc * 100)))
            self.realistic_check.setChecked(bool(settings.realistic_flight))
            self.arc_by_distance_check.setChecked(bool(getattr(settings, "arc_by_distance", False)))
            self.arc_slider.setEnabled(not settings.realistic_flight)
            self.arc_spin.setEnabled(not settings.realistic_flight)
        finally:
            self._syncing = False
        self._refresh_preview()
        self._refresh_controls()

    def reset_to_retail(self) -> None:
        self._syncing = True
        try:
            self.catch_check.setChecked(False)
            self.scorebug_check.setChecked(False)
            self.accel_check.setChecked(False)
            self.draft_check.setChecked(False)
            self.returner_check.setChecked(False)
            self.progression_check.setChecked(False)
            self.edge_check.setChecked(False)
        finally:
            self._syncing = False
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
        settings = self.settings()
        curves = dict(tt.curves_for(settings))
        curves["lobspeed"] = tt.effective_lobspeed(settings, curves)
        return tt.preview(curves)

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
            self, "Choose your game disc (.iso) or default.xbe", str(Path.home()), SOURCE_FILTER,
        )
        if chosen:
            self.load_source(Path(chosen))

    def load_source(self, source: Path, *, quiet: bool = False) -> None:
        """Read the curve tables from ``source`` in the background.

        ``quiet`` (the open-disc hook) keeps a read failure on the status line: the hook
        fills every page at once, and a dialog from a page nobody asked would block them all."""

        if self._busy:
            return
        self._quiet_failure = bool(quiet)

        def done(result: object) -> None:
            assert isinstance(result, dict)
            self._quiet_failure = False
            self.apply_report(result)

        self._run(lambda progress: tt.read_any(source), done)

    def apply_report(self, report: dict[str, object]) -> None:
        """Populate the panel from a ``read_any`` report (also used by tests)."""

        self._report = report
        self.source_field.setText(str(report["path"]))
        is_image = tt.is_disc_image(str(report["path"]))
        source_caption, target_caption = source_captions(is_image)
        self.source_caption.setText(source_caption)
        self.target_caption.setText(target_caption)
        self.write_button.setText(write_caption(is_image))
        if is_image and (not self.target_field.text().strip() or getattr(self, "_target_generated", False)):
            self.target_field.setText(suggest_copy_name(str(report["path"]), suffix="throw tuned"))
            self._target_generated = True
        settings = report["settings"]
        assert isinstance(settings, tt.TuningSettings)
        self.set_settings(settings)
        curves = report["curves"]
        assert isinstance(curves, dict)
        edited = [name for name in tt.EDITABLE_CURVES if not curves[name]["retail"]]
        catch_state = str(report.get("catch_slider", "foreign"))
        self._syncing = True
        try:
            self.catch_check.setChecked(catch_state == "applied")
            self.catch_check.setEnabled(catch_state != "foreign")
        finally:
            self._syncing = False
        if catch_state == "applied":
            self.catch_check.setToolTip("Already applied in this source; it cannot be removed here (start from retail).")
        scorebug_state = "n/a"
        if report.get("container") == "xiso":
            try:
                scorebug_state = self._scorebug_module().status(Path(str(report["path"])))
            except Exception:  # noqa: BLE001 - the layout tool refuses anything it cannot prove
                scorebug_state = "foreign"
        self._scorebug_state = scorebug_state
        self._syncing = True
        try:
            self.scorebug_check.setChecked(scorebug_state == "applied")
            self.scorebug_check.setEnabled(scorebug_state == "retail")
        finally:
            self._syncing = False
        if scorebug_state == "applied":
            self.scorebug_check.setToolTip("Already applied in this source; it cannot be removed here (start from retail).")
        elif scorebug_state == "n/a":
            self.scorebug_check.setToolTip("Open a disc image (.iso) to use this; a bare default.xbe has no scorebug mesh.")
        accel_state = str(report.get("accel_ramp", "foreign"))
        self._syncing = True
        try:
            self.accel_check.setChecked(accel_state == "applied")
            self.accel_check.setEnabled(accel_state != "foreign")
        finally:
            self._syncing = False
        if accel_state == "applied":
            self.accel_check.setToolTip("Already applied in this source; it cannot be removed here (start from retail).")
        draft_state = str(report.get("draft_ai", "foreign"))
        self._syncing = True
        try:
            self.draft_check.setChecked(draft_state == "applied")
            self.draft_check.setEnabled(draft_state != "foreign")
        finally:
            self._syncing = False
        if draft_state == "applied":
            self.draft_check.setToolTip("Already applied in this source; it cannot be removed here (start from retail).")
        for box, key in ((self.returner_check, "returner_fix"), (self.progression_check, "progression")):
            box_state = str(report.get(key, "foreign"))
            self._syncing = True
            try:
                box.setChecked(box_state == "applied")
                box.setEnabled(box_state != "foreign")
            finally:
                self._syncing = False
            if box_state == "applied":
                box.setToolTip("Already applied in this source; it cannot be removed here (start from retail).")
        edge_state = str(report.get("edge_rename", "foreign"))
        edge_disc = report.get("edge_rename_disc")
        edge_disc_state = str(edge_disc.get("status")) if isinstance(edge_disc, dict) else "n/a"
        # a disc whose XBE is already renamed but whose text is still retail can still take the text pass
        edge_writable = edge_state == "retail" or (edge_state == "applied" and edge_disc_state == "retail")
        self._edge_writable = edge_writable
        self._syncing = True
        try:
            self.edge_check.setChecked(edge_state == "applied" and not edge_writable)
            self.edge_check.setEnabled(edge_writable)
        finally:
            self._syncing = False
        if edge_state == "applied" and not edge_writable:
            self.edge_check.setToolTip("Already applied in this source; it cannot be removed here (start from retail).")
        container = "disc image" if report.get("container") == "xiso" else "default.xbe"
        retail = " (retail default.xbe by SHA-256)" if report.get("matches_retail_sha256") else ""
        state = ("retail throw tables" if not edited
                 else "already tuned: " + ", ".join(edited) + " edited")
        flight = ("arc by distance (45-60 high, 63+ flat)" if getattr(settings, "arc_by_distance", False)
                  else "realistic flight" if settings.realistic_flight else f"arc {int(round(settings.arc * 100))} %")
        catch_text = {"retail": "catch patch not applied", "applied": "catch patch applied",
                      "foreign": "catch-patch sites unrecognised (patch disabled)"}[catch_state]
        extras = []
        if scorebug_state in ("applied", "retail"):
            extras.append("ESPN scorebug " + ("applied" if scorebug_state == "applied" else "not applied"))
        if accel_state in ("applied", "retail"):
            extras.append("acceleration ramp " + ("applied" if accel_state == "applied" else "not applied"))
        if draft_state in ("applied", "retail"):
            extras.append("draft AI " + ("applied" if draft_state == "applied" else "not applied"))
        for key, label in (("returner_fix", "returner fix"), ("progression", "progression")):
            if str(report.get(key)) in ("applied", "retail"):
                extras.append(label + " " + ("applied" if report.get(key) == "applied" else "not applied"))
        if edge_state in ("applied", "retail"):
            extras.append("EDGE rename " + ("applied" if edge_state == "applied" else "not applied")
                          + (f" (disc text {edge_disc_state})" if edge_disc_state != "n/a" else ""))
        self.source_status.setText(
            f"Read the {container}{retail}: {state}. Current ceiling "
            f"{settings.max_deep_yards:g} yd, {flight}; {catch_text}"
            + ("; " + "; ".join(extras) if extras else "") + "."
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
            self, "Where should the new disc go?" if is_image else "Save the patched executable as", default_name,
            IMAGE_FILTER if is_image else XBE_FILTER,
        )
        if chosen:
            self.target_field.setText(chosen)
            self._target_generated = False
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
        curve_change = any(
            tuple(wanted[name]) != tuple(curves[name]["points"])  # type: ignore[index]
            for name in tt.EDITABLE_CURVES
        )
        catch_change = self.catch_check.isChecked() and str(self._report.get("catch_slider")) == "retail"
        scorebug_change = self.scorebug_check.isChecked() and getattr(self, "_scorebug_state", "n/a") == "retail"
        accel_change = self.accel_check.isChecked() and str(self._report.get("accel_ramp")) == "retail"
        draft_change = self.draft_check.isChecked() and str(self._report.get("draft_ai")) == "retail"
        returner_change = self.returner_check.isChecked() and str(self._report.get("returner_fix")) == "retail"
        progression_change = self.progression_check.isChecked() and str(self._report.get("progression")) == "retail"
        edge_change = self.edge_check.isChecked() and getattr(self, "_edge_writable", False)
        return (curve_change or catch_change or scorebug_change or accel_change or draft_change or edge_change
                or returner_change or progression_change)

    def _write(self) -> None:
        source_text = self.source_field.text()
        target_text = self.target_field.text()
        if not source_text or not target_text or not self.has_changes():
            return
        source = Path(source_text)
        target = Path(target_text)
        settings = self.settings()
        want_catch = self.catch_check.isChecked() and str(self._report.get("catch_slider") if self._report else "") == "retail"
        want_scorebug = self.scorebug_check.isChecked() and getattr(self, "_scorebug_state", "n/a") == "retail"
        want_accel = self.accel_check.isChecked() and str(self._report.get("accel_ramp") if self._report else "") == "retail"
        want_draft = self.draft_check.isChecked() and str(self._report.get("draft_ai") if self._report else "") == "retail"
        want_edge = self.edge_check.isChecked() and getattr(self, "_edge_writable", False)
        want_returner = self.returner_check.isChecked() and str(self._report.get("returner_fix") if self._report else "") == "retail"
        want_progression = self.progression_check.isChecked() and str(self._report.get("progression") if self._report else "") == "retail"
        overwrite = target.exists()
        is_image = tt.is_disc_image(source)
        if want_scorebug and not (is_image and tt.is_disc_image(target)):
            QMessageBox.warning(self, "Disc image needed",
                                "The ESPN scorebug edits the field resource pack, so both the source and the "
                                "copy must be disc images (.iso).")
            return
        top = self.preview_rows()[-1]
        confirmation = QMessageBox.question(
            self,
            "Make disc with these changes?" if is_image else "Save a patched executable?",
            f"Ceiling {settings.max_deep_yards:g} yd at 99 arm, arc {int(round(settings.arc * 100))} % "
            f"({top.hang_seconds:.1f} s hang, {top.apex_yards:.0f} yd apex on the longest ball)"
            + ("\nCatching/Interception-slider patch: ON (executable patch, Catching menu max 200)" if want_catch else "")
            + ("\nModern ESPN scorebug: ON (mesh re-layout, bottom centre, atlas + ESPN strip repainted)" if want_scorebug else "")
            + ("\nAcceleration ramp: ON (executable patch, players wind up to top speed)" if want_accel else "")
            + ("\nRealistic CPU drafts and free agency: ON (executable patch, draft pick + free-agent wishes)" if want_draft else "")
            + ("\nReturner fix: ON (executable patch, franchise auto depth chart)" if want_returner else "")
            + ("\nNFL-shaped development: ON (aging curves + archetype weights)" if want_progression else "")
            + ("\nEDGE rename: ON (position tables, long names, formation slots" + (", historic-roster names, trivia" if is_image else "") + ")" if want_edge else "")
            + f"\n\nSource (unchanged): {source}\n"
            + (f"Replace existing copy: {target}" if overwrite else f"New {'disc' if is_image else 'executable'}: {target}")
            + ("\n\nThis copies the whole disc, then patches default.xbe inside the copy."
               if is_image else "")
            + "\n\n" + XEMU_LINE,
            QMessageBox.Ok | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )
        if confirmation != QMessageBox.Ok:
            return

        scorebug_module = self._scorebug_module() if want_scorebug else None

        def write(progress: ProgressSink) -> dict[str, object]:
            progress("Patching throw tables", 0, 0)
            result = tt.write_copy(source, target, settings=settings, overwrite=overwrite, progress=progress,
                                   catch_slider=want_catch, accel_ramp=want_accel, draft_ai=want_draft,
                                   edge_rename=want_edge, returner_fix=want_returner, progression=want_progression)
            if scorebug_module is not None:
                progress("Re-laying the scorebug (mesh, placement, textures)", 0, 0)
                receipt = scorebug_module.apply_in_place(target)
                result = dict(result)
                result["scorebug_layout"] = receipt
            return result

        def done(result: object) -> None:
            assert isinstance(result, dict)
            changes = result.get("changes") or []
            summary = ", ".join(str(change["curve"]) for change in changes)
            if result.get("catch_slider") == "applied" and want_catch:
                summary = (summary + ", " if summary else "") + "catch-slider patch"
            if result.get("scorebug_layout"):
                summary = (summary + ", " if summary else "") + "ESPN scorebug"
            if result.get("accel_ramp") == "applied" and want_accel:
                summary = (summary + ", " if summary else "") + "acceleration ramp"
            if result.get("draft_ai") == "applied" and want_draft:
                summary = (summary + ", " if summary else "") + "realistic CPU drafts"
            if result.get("edge_rename") == "applied" and want_edge:
                summary = (summary + ", " if summary else "") + "EDGE rename"
            if result.get("returner_fix") == "applied" and want_returner:
                summary = (summary + ", " if summary else "") + "returner fix"
            if result.get("progression") == "applied" and want_progression:
                summary = (summary + ", " if summary else "") + "NFL-shaped development"
            self.status_label.setText(
                f"{'Disc ready' if is_image else 'Patched executable saved'}: {target.name}. Changes: {summary} "
                f"({result.get('changed_byte_count')} bytes changed, read-back verified)."
            )
            QMessageBox.information(
                self,
                "Disc ready" if is_image else "Patched executable saved",
                f"{target}\n\nChanges: {summary}.\n\n" + XEMU_LINE,
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
        task.signals.result.connect(bound(self, on_success))
        task.signals.error.connect(self._failed)

        def finished() -> None:
            self._tasks.discard(task)
            if self._busy:
                self._busy = False
                self.operation_state_changed.emit(False)
            self.progress_bar.hide()
            self.progress_label.setText("")
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
        self.status_label.setText(f"Failed: {message}")
        self.error_raised.emit(message)
        if getattr(self, "_quiet_failure", False):
            self._quiet_failure = False
            self.source_status.setText(f"Couldn't read this file's throw tables: {message}")
            return
        show_operation_error(self, "finish the throw tuning", message)

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
