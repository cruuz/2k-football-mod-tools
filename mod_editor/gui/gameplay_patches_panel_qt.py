"""Gameplay Patches tab: the executable patches that change how the game plays, in one place.

Each toggle explains what the retail game does, what the patch changes, and what to expect.
Writing goes through mod_editor.core.mod_build so a copy carries exactly the ticked patches and
one receipt.  The throw curve tables keep their own richer editor (Throw Distance & Arc).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PyQt5.QtCore import QObject, QRunnable, Qt, QThreadPool, pyqtSignal
from PyQt5.QtWidgets import (
    QCheckBox,
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

from mod_editor.core import mod_build
from mod_editor.core import nfl2k5_throw_tuning as tt

SOURCE_FILTER = "NFL 2K5 default.xbe or disc image (default.xbe *.xbe *.xiso *.iso *.img);;All files (*)"

PATCHES = (
    ("catch_slider", "Catching and Interception sliders decide the outcome",
     "Retail: the Catching slider barely reaches play and the Interception slider is scaled by difficulty "
     "and floored at a 10 % pick chance, which is why the forums call it broken. Patch: the catch roll is "
     "divided by twice the receiver's side's Catching slider (goes to 200) and a defender's roll by twice the "
     "Interception slider (0 = no picks, 50 = retail, 100 = double)."),
    ("accel_ramp", "Acceleration ramp",
     "Retail has no acceleration: everyone is at top speed on the first step, so linemen keep pace with "
     "receivers and slow quarterbacks burst out of the pocket. Patch: players wind up from 60 % to 100 % of "
     "their Speed rating, about 1 s at 99 Agility and 2 s at 30; standing still resets it."),
    ("draft_ai", "Realistic, unpredictable CPU drafts and free agency in franchise",
     "Retail: on the clock a CPU team takes the best raw overall among its neediest positions, and raw "
     "overall is compared across positions, so the positions whose rookies roll the highest overalls (HB, DE, "
     "T, QB) fill round 1 and the 11th-best HB goes as soon as HB is a top-three need. Patch: the pick is the "
     "prospect with the best edge over his own position's class average, times real positional value, plus "
     "the team's need order and a little noise; CPU free-agent targets are scored the same way."),
    ("returner_fix", "Real kick and punt returners on CPU depth charts",
     "Retail: the franchise auto depth chart never records which player had the best punt-return score; it "
     "stores the score itself as the roster slot, so the punt returner is whoever sits in slot 0 (often a QB), "
     "and the second kick returner is chosen on a stale score. Patch: returners are tracked by player over "
     "the whole roster, starters stay off the units unless nobody else is eligible, and only WR, CB, S, RB and "
     "FB can return."),
    ("progression", "NFL-shaped player development",
     "Retail: development is a hidden archetype per player driving flat aging curves (+2 or +3 from rookie "
     "year to the prime), so the draft-day rating is the career. Patch (data only): the ten aging-curve tables "
     "grow over years 1-5 by rating family and decline harder after year 9-12 (speed first), and each "
     "position's archetype mix is widened so more prospects become stars or busts. Draft-day ratings are "
     "unchanged."),
    ("kick_rules", "Modern kicking: kickoff from the 35, touchbacks to the 35, PAT from the 15, ~70-yard legs",
     "Retail kicks off from the 30 with touchbacks at the 20, snaps the extra point from the 2, and its "
     "field-goal tables top out near 60 yards for a 99 kicker on a perfect meter. Patch: kickoff spot 35, "
     "touchback 35 (2026 rule), PAT snapped from the 15 (two-point tries stay at the 2), and the meter and kicker "
     "curves re-spaced as a scale so a 99 leg reaches 65-69 yards while mid-power kickers gain 2-3. "
     "Kickoff and return formations follow the ball; onside and safety kicks are untouched; the CPU keeps "
     "its retail field-goal range for fourth-down decisions."),
    ("overtime", "Modern overtime: both teams get a possession, 10 minutes with ties, playoffs to a winner",
     "Retail overtime is sudden death for the quarter length: any score ends it, even a first-possession "
     "touchdown, and the regular season ties after one period. Patch (the 2025 NFL rule): each team is "
     "guaranteed a possession unless the kicking team scores a safety; after both have possessed the leader "
     "wins or the next score wins; regular-season overtime is one 10-minute period (scaled with the quarter "
     "length) and can tie; the postseason keeps playing, including through an unfinished second possession. "
     "The franchise sim engine gets the 10-minute clock and the one-period tie; its own sudden-death rule is "
     "left as is."),
    ("camera", "Default camera: Standard becomes the Far look",
     "Retail's Standard camera uses a 35 lens 8 yards behind the quarterback; the Far preset is the same "
     "geometry through a wider 28 lens (24 with the ball in the air). Patch: the seven live-play records of "
     "the Standard preset take Far's look-at, lens and offset words, so a profile left on Standard gets the "
     "Far view. Far itself, the kick, replay and other presets are untouched; the fresh-profile default stays "
     "Standard."),
    ("seven_on_seven", "7-on-7 practice mode",
     "Retail Practice offers Special Move, Full Scrimmage, Offense Only and Kickoff. Patch: Practice -> Scrimmage -> "
     "Practice Type gains 7-On-7, which plays as Full Scrimmage with the practice playbook loaded for both teams and "
     "the pass rush off; the practice book gains three 7-on-7 passing sets (Trips, Spread, Ace: QB, a centre to snap, "
     "five skill players) with nine pass concepts and two coverage sets (4-3 and Nickel looks) with six coverages. The "
     "engine always fields eleven, so the four linemen of each side stand idle at the sideline by design, and one "
     "parked defender rushes after a 4-second count as the throw timer. Needs a disc image; unwitnessed in game."),
)


class _Signals(QObject):
    progress = pyqtSignal(str)
    finished = pyqtSignal(object)
    failed = pyqtSignal(str)


class _Task(QRunnable):
    def __init__(self, operation: Callable[[Callable[[str, int, int], None]], object]) -> None:
        super().__init__()
        self.signals = _Signals()
        self._operation = operation
        self.setAutoDelete(False)

    def run(self) -> None:
        try:
            result = self._operation(lambda msg, _a, _b: self.signals.progress.emit(msg))
        except Exception as exc:  # noqa: BLE001
            self.signals.failed.emit(f"{type(exc).__name__}: {exc}")
        else:
            self.signals.finished.emit(result)


TEXT_PATCHES = (
    ("edge_rename", "Rename DE to EDGE everywhere",
     "Retail calls the position DE / Defensive End in rosters, depth charts, the draft, the formation "
     "editor and the scorebug legend. Patch: every one of those strings reads EDGE (the executable's six "
     "position tables plus the disc's own text spans), so the game speaks modern NFL. Formation slots "
     "LDE/RDE show EDGE; abbreviation fields keep four letters."),
    ("scheme_labels", "Depth-chart positions by scheme (MIKE / SAM / WILL, EDGE, NT)",
     "Retail labels every linebacker slot ILB / ROLB / LOLB and every 3-4 lineman DT / DE. Patch: the 4-3 depth "
     "chart reads SAM, MIKE, WILL; the 3-4 chart reads EDGE for the outside backers, MIKE and WILL inside, NT in "
     "the middle. Labels only (each scheme has its own slot records); who fills a slot is unchanged."),
)


class GameplayPatchesPanel(QWidget):
    """A page of executable/text toggles written through mod_build.

    ``patches`` chooses which toggles the page shows (``PATCHES`` for gameplay, ``TEXT_PATCHES`` for
    the EDGE rename); each key must be a BuildPlan field and an ``inspect`` state key.
    """

    def __init__(self, facade: object | None = None, parent: QWidget | None = None, *,
                 patches: tuple[tuple[str, str, str], ...] = PATCHES,
                 title: str = "Gameplay Patches",
                 intro: str = "Executable patches that change how the game plays.") -> None:
        super().__init__(parent)
        self._facade = facade
        self._pool = QThreadPool(self)
        self._task: _Task | None = None
        self._state: dict[str, object] | None = None
        self.checks: dict[str, QCheckBox] = {}
        self._patches = tuple(patches)
        self._title = title
        self._intro = intro
        self._build_ui()
        self._refresh()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 22)
        root.setSpacing(12)
        title = QLabel(self._title)
        title.setObjectName("throwTitle")
        root.addWidget(title)
        intro = QLabel(self._intro + " Each writes a copy; the source is never "
                       "touched. xemu-only (the RSA signature stays stale). For a release copy with everything, "
                       "use Build & Share → Build.")
        intro.setObjectName("throwMuted")
        intro.setWordWrap(True)
        root.addWidget(intro)
        src = QHBoxLayout()
        src.addWidget(QLabel("Source"))
        self.source_field = QLineEdit()
        self.source_field.setReadOnly(True)
        src.addWidget(self.source_field, 1)
        self.source_button = QPushButton("Choose…")
        self.source_button.clicked.connect(self._choose_source)
        src.addWidget(self.source_button)
        root.addLayout(src)
        self.source_status = QLabel("Choose a default.xbe or a disc image to read which patches it already carries.")
        self.source_status.setObjectName("throwMuted")
        self.source_status.setWordWrap(True)
        root.addWidget(self.source_status)
        for key, label, explanation in self._patches:
            box = QGroupBox(label)
            lay = QVBoxLayout(box)
            check = QCheckBox("Apply to the copy")
            check.toggled.connect(lambda _c: self._refresh())
            lay.addWidget(check)
            text = QLabel(explanation)
            text.setObjectName("throwMuted")
            text.setWordWrap(True)
            lay.addWidget(text)
            root.addWidget(box)
            self.checks[key] = check
        out = QHBoxLayout()
        out.addWidget(QLabel("Write copy to"))
        self.target_field = QLineEdit()
        out.addWidget(self.target_field, 1)
        self.target_button = QPushButton("Choose…")
        self.target_button.clicked.connect(self._choose_target)
        out.addWidget(self.target_button)
        root.addLayout(out)
        actions = QHBoxLayout()
        self.write_button = QPushButton("Write patched copy")
        self.write_button.clicked.connect(self._write)
        actions.addWidget(self.write_button)
        actions.addStretch(1)
        root.addLayout(actions)
        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)
        root.addStretch(1)

    def apply_state(self, state: dict[str, object]) -> None:
        self._state = state
        self.source_field.setText(str(state.get("path", "")))
        for key, _label, _e in self._patches:
            value = str(state.get(key))
            check = self.checks[key]
            check.setEnabled(value == "retail")
            check.setChecked(False)
            check.setToolTip({"applied": "Already applied in this source.",
                              "foreign": "Bytes at the patch sites are neither retail nor this patch; refusing.",
                              "retail": ""}.get(value, "Unknown state."))
        self.source_status.setText("Read: " + "; ".join(f"{k}: {state.get(k)}" for k, _l, _e in self._patches) + ".")
        self._refresh()

    def plan(self) -> mod_build.BuildPlan:
        plan = mod_build.BuildPlan(
            source=self.source_field.text(), target=self.target_field.text(),
            overwrite=Path(self.target_field.text()).exists() if self.target_field.text() else False,
        )
        for key, check in self.checks.items():
            setattr(plan, key, check.isChecked())
        return plan

    def _refresh(self) -> None:
        any_on = any(c.isChecked() for c in self.checks.values())
        self.write_button.setEnabled(any_on and bool(self.source_field.text()) and bool(self.target_field.text()) and self._task is None)

    def _choose_source(self) -> None:
        chosen, _f = QFileDialog.getOpenFileName(self, "Choose default.xbe or a disc image", str(Path.home()), SOURCE_FILTER)
        if not chosen:
            return
        try:
            self.apply_state(mod_build.inspect(Path(chosen)))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Could not read the source", str(exc))

    def _choose_target(self) -> None:
        is_image = bool(self.source_field.text()) and tt.is_disc_image(self.source_field.text())
        chosen, _f = QFileDialog.getSaveFileName(self, "Choose where to save the patched copy",
                                                 "ESPN NFL 2K5 (gameplay patched).xiso.iso" if is_image else "default_patched.xbe")
        if chosen:
            self.target_field.setText(chosen)
            self._refresh()

    def _write(self) -> None:
        plan = self.plan()
        if not any(check.isChecked() for check in self.checks.values()):
            return
        answer = QMessageBox.question(self, "Write a patched copy?",
                                      f"Source (untouched): {plan.source}\n" + ("REPLACING: " if plan.overwrite else "New copy: ") + plan.target
                                      + "\n\nxemu-only: the RSA signature stays stale.",
                                      QMessageBox.Ok | QMessageBox.Cancel, QMessageBox.Cancel)
        if answer != QMessageBox.Ok:
            return
        task = _Task(lambda progress: mod_build.build(plan, progress))
        task.signals.progress.connect(self.status_label.setText)
        task.signals.finished.connect(self._done)
        task.signals.failed.connect(self._failed)
        self._task = task
        self._refresh()
        self._pool.start(task)

    def _done(self, receipt: object) -> None:
        self._task = None
        assert isinstance(receipt, dict)
        self.status_label.setText(f"Written: {Path(str(receipt.get('target'))).name}.")
        try:
            self.apply_state(mod_build.inspect(Path(str(receipt.get("target")))))
        except Exception:  # noqa: BLE001
            pass
        self._refresh()

    def _failed(self, message: str) -> None:
        self._task = None
        self.status_label.setText(f"Failed: {message}")
        QMessageBox.critical(self, "Write failed", message)
        self._refresh()


__all__ = ["PATCHES", "TEXT_PATCHES", "GameplayPatchesPanel"]
