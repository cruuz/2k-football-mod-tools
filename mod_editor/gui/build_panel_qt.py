"""Build page: every patch in one place, one source, one copy, one receipt.

Sits under the "Build & Share" navigation entry.  It reads the current state of a default.xbe or
disc image (mod_editor.core.mod_build.inspect), shows every patch as a grouped toggle with its
parameters, and writes one patched copy through mod_editor.core.mod_build.build in a background
thread.  Optional modules that are not present in this build are shown disabled with the reason.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PyQt5.QtCore import QObject, QRunnable, Qt, QThreadPool, pyqtSignal
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from mod_editor.core import mod_build
from mod_editor.core import nfl2k5_player_star as player_star
from mod_editor.core import nfl2k5_throw_tuning as tt
from mod_editor.gui.ux_text import NOT_TESTED, XEMU_LINE, Details, plain_failure, show_operation_error, source_captions, suggest_copy_name, tab_title

SOURCE_FILTER = "NFL 2K5 default.xbe or disc image (default.xbe *.xbe *.xiso *.iso *.img);;All files (*)"
IMAGE_FILTER = "Xbox disc images (*.xiso *.iso *.img);;All files (*)"
XBE_FILTER = "Xbox executables (default.xbe *.xbe);;All files (*)"


PRESET_LABELS = {"softdrink_basic": "Basic", "softdrink_advanced": "Modern", "softdrink_experimental": "Experimental"}
PRESET_BUTTONS = {"softdrink_basic": "Basic — 2004 fixes",
                  "softdrink_advanced": "Modern — updated gameplay & season",
                  "softdrink_experimental": "Experimental — extra changes"}
PRESET_CAPTIONS = {
    "softdrink_basic": ("2004 season and rules. Throw/catching fixes, Franchise draft and free agency, CPU returners, "
                        "kicking power, Player Card team column, Edit Player position and Pro Bowl tab order."),
    "softdrink_advanced": ("Basic plus acceleration, progression, position changes, modern rules, 2026 season, "
                           "presentation and other selected changes. Includes changes not yet tested in-game."),
    "softdrink_experimental": ("Modern plus widescreen, dynamic kickoff alignment and kick laces. "
                               "Includes changes not yet tested in-game."),
}
PRESET_NOTE = "Review the selected changes below. Unavailable or already-installed changes are listed here."


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


class BuildPanel(QWidget):
    """One-stop build of every patch into a single copy."""

    built = pyqtSignal(dict)   # the receipt of the copy just written (Share pre-fills from it)

    def __init__(self, facade: object | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._facade = facade
        self._pool = QThreadPool(self)
        self._task: _Task | None = None
        self._state: dict[str, object] | None = None
        self._available = mod_build.availability()
        self._reading = False                 # the shell is inspecting the open disc for us
        self._target_generated = False        # the target was suggested, not chosen by the user
        self.pending_preset: str | None = None  # Getting Started asked for a preset before the disc was read
        # direct inputs the option list edits (initialised before the UI so the first refresh can read them)
        self.commentary: list[mod_build.CommentarySwap] = []
        self.star_players: list[str] = []
        self._star_names: list[str] = []
        self.playbook_packs: list[str] = []
        self._build_ui()
        self._refresh()

    # ---------------------------------------------------------------- UI
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 22)
        root.setSpacing(12)
        title = QLabel("Build")
        title.setObjectName("throwTitle")
        root.addWidget(title)
        intro = QLabel("Choose a preset or select changes, then Make my disc. The source stays unchanged. "
                       "This uses the selections on this tab; project edits (art, text, audio) use Make disc "
                       "from project on their own pages. " + XEMU_LINE)
        intro.setObjectName("throwMuted")
        intro.setWordWrap(True)
        root.addWidget(intro)

        src = QHBoxLayout()
        self.source_caption = QLabel("Game disc (.iso)")
        src.addWidget(self.source_caption)
        self.source_field = QLineEdit()
        self.source_field.setPlaceholderText("Filled in when you open a disc (top right), or choose a disc / default.xbe here")
        self.source_field.setReadOnly(True)
        src.addWidget(self.source_field, 1)
        self.source_button = QPushButton("Choose…")
        self.source_button.clicked.connect(self._choose_source)
        src.addWidget(self.source_button)
        root.addLayout(src)
        self.source_status = QLabel("Open your game disc (top right), or choose a disc / default.xbe here, to read what it already carries.")
        self.source_status.setObjectName("throwMuted")
        self.source_status.setWordWrap(True)
        root.addWidget(self.source_status)

        # One click to start from a known-good set, then customise below.
        # The checklist IS the product: make every toggle read at a glance (big indicator, accent when ticked).
        self.setStyleSheet(
            "QGroupBox { font-weight: 600; margin-top: 14px; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }"
            "QCheckBox { padding: 4px 2px; spacing: 10px; }"
            "QCheckBox::indicator { width: 20px; height: 20px; border: 2px solid #8a94a6; border-radius: 4px; background: #1b1f27; }"
            "QCheckBox::indicator:unchecked:hover { border-color: #c9d1de; }"
            "QCheckBox::indicator:checked { background: #2ecc71; border-color: #2ecc71; "
            "image: url(:/qt-project.org/styles/commonstyle/images/standardbutton-apply-16.png); }"
            "QCheckBox::indicator:disabled { border-color: #4a5060; background: #22262e; }"
            "QCheckBox:checked { color: #d8ffe6; font-weight: 600; }"
            "QCheckBox:disabled { color: #6b7385; }"
            "QCheckBox::indicator:focus { border-color: #6ee7c7; }"
            "QLabel#optionBadge { color: #f3d27a; background: #2a2a1c; border: 1px solid #6a5a2a; border-radius: 6px; padding: 1px 6px; }"
            "QPushButton#presetButton { padding: 8px 14px; font-weight: 600; }")
        presets = QGroupBox("Choose a SOFTDRINK preset")
        pr = QVBoxLayout(presets)
        preset_grid = QGridLayout()
        preset_grid.setHorizontalSpacing(14)
        self.preset_basic_button = QPushButton(tab_title(PRESET_BUTTONS["softdrink_basic"]))
        self.preset_advanced_button = QPushButton(tab_title(PRESET_BUTTONS["softdrink_advanced"]))
        self.preset_experimental_button = QPushButton(tab_title(PRESET_BUTTONS["softdrink_experimental"]))
        self.preset_captions: dict[str, QLabel] = {}
        for column, (name, button) in enumerate((("softdrink_basic", self.preset_basic_button),
                                                 ("softdrink_advanced", self.preset_advanced_button),
                                                 ("softdrink_experimental", self.preset_experimental_button))):
            button.setObjectName("presetButton")
            button.setToolTip(PRESET_CAPTIONS[name])
            button.setAccessibleName(f"{PRESET_LABELS[name]} preset")
            button.setAccessibleDescription(PRESET_CAPTIONS[name])
            button.clicked.connect(lambda _c=False, key=name: self.apply_preset(key))
            caption = QLabel(PRESET_CAPTIONS[name])
            caption.setObjectName("throwMuted")
            caption.setWordWrap(True)
            caption.setAlignment(Qt.AlignTop | Qt.AlignLeft)
            self.preset_captions[name] = caption
            preset_grid.addWidget(button, 0, column)
            preset_grid.addWidget(caption, 1, column)
            preset_grid.setColumnStretch(column, 1)
        pr.addLayout(preset_grid)
        self.preset_note = QLabel(PRESET_NOTE)
        self.preset_note.setObjectName("throwMuted")
        self.preset_note.setWordWrap(True)
        pr.addWidget(self.preset_note)
        root.addWidget(presets)

        # The disc, the copy and the button come BEFORE the long option list, so the one
        # thing the first-run path needs is never off-screen (BS-03 / BS-10).
        make = QGroupBox("Make my disc")
        mk = QVBoxLayout(make)
        out = QHBoxLayout()
        self.target_caption = QLabel("Save disc copy as")
        out.addWidget(self.target_caption)
        self.target_field = QLineEdit()
        self.target_field.setPlaceholderText("Where the new disc goes (a new file; suggested beside your disc)")
        out.addWidget(self.target_field, 1)
        self.target_button = QPushButton("Choose…")
        self.target_button.clicked.connect(self._choose_target)
        out.addWidget(self.target_button)
        self.target_field.textEdited.connect(lambda _t: self._user_target())
        self.target_field.textChanged.connect(lambda _t: self._refresh())
        mk.addLayout(out)
        self.summary_label = QLabel("Selected: nothing yet.")
        self.summary_label.setObjectName("throwMuted")
        self.summary_label.setWordWrap(True)
        mk.addWidget(self.summary_label)
        actions = QHBoxLayout()
        self.build_button = QPushButton("Make my disc")
        self.build_button.setObjectName("primaryButton")
        self.build_button.clicked.connect(self._build)
        actions.addWidget(self.build_button)
        self.blocker_label = QLabel("")
        self.blocker_label.setObjectName("throwMuted")
        self.blocker_label.setWordWrap(True)
        self.blocker_label.setAccessibleName("Why Make my disc is unavailable")
        actions.addWidget(self.blocker_label, 1)
        mk.addLayout(actions)
        prog = QHBoxLayout()
        self.progress_label = QLabel("")
        self.progress_label.setObjectName("throwMuted")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.hide()
        prog.addWidget(self.progress_label, 1)
        prog.addWidget(self.progress_bar)
        mk.addLayout(prog)
        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        mk.addWidget(self.status_label)
        root.addWidget(make)

        # ---------------------------------------------------------------- the option list
        # Every BuildPlan field is on this page (E4).  Each row is a real QCheckBox (its text is
        # the accessible name, label-click toggles it, Space toggles it) with a one-line helper
        # under it and a small qualifier badge: Full disc required / Already installed / Not yet
        # tested in-game / New franchises only / Not available in this release.  The long
        # technical story sits under Details so the labels never push the page wide.
        self._helpers: dict[str, QLabel] = {}
        self._badges: dict[str, QLabel] = {}
        self._static_badges: dict[str, str] = {}
        self._needs_image: set[str] = set()
        options = QGroupBox("Choose changes")
        ol = QVBoxLayout(options)
        ol.setSpacing(10)
        self.options_hint = QLabel("A preset ticks a known-good set; untick anything here, or tick more. "
                                   "Badges say when a change needs the full disc, is already on the disc, or is not yet tested in-game.")
        self.options_hint.setObjectName("throwMuted")
        self.options_hint.setWordWrap(True)
        ol.addWidget(self.options_hint)

        # ---- Gameplay
        gameplay = QGroupBox("Gameplay")
        g = QVBoxLayout(gameplay)
        self.throw_check = self._option(g, "throw", "Change throw distance",
                                        "How far the strongest arm can throw; the original maximum at 99 Pass Arm Strength is 55 yards.")
        throw_row = QHBoxLayout()
        throw_row.addSpacing(30)
        throw_row.addWidget(QLabel("Longest throw at 99 Pass Arm Strength"))
        self.ceiling_spin = QSpinBox()
        self.ceiling_spin.setRange(int(tt.MIN_MAX_DEEP_YARDS), int(tt.MAX_MAX_DEEP_YARDS))
        self.ceiling_spin.setValue(80)
        self.ceiling_spin.setSuffix(" yd")
        self.ceiling_spin.setAccessibleName("Longest throw at 99 Pass Arm Strength, in yards")
        throw_row.addWidget(self.ceiling_spin)
        throw_row.addStretch(1)
        g.addLayout(throw_row)
        flight_row = QHBoxLayout()
        flight_row.addSpacing(30)
        self.realistic_check = QCheckBox("Realistic deep-ball flight")
        self.realistic_check.setChecked(True)
        self.realistic_check.setToolTip("The speed table elite NFL arms actually produce: 3.2-3.9 s hang for 60-80 air yards. "
                                        "Overrides the manual arc below.")
        flight_row.addWidget(self.realistic_check)
        self.arc_by_distance_check = QCheckBox("Higher arc on 45–60 yard lobs")
        self.arc_by_distance_check.setToolTip("Throws up to 40 yards keep the original speeds, 45-60 air yards get a high hanging arc, "
                                              "63 yards and beyond keep the realistic flat flight.")
        flight_row.addWidget(self.arc_by_distance_check)
        flight_row.addStretch(1)
        g.addLayout(flight_row)
        self.throw_details = Details("Throw options")
        arc_row = QHBoxLayout()
        arc_row.addWidget(QLabel("Manual deep-ball arc (%)"))
        self.arc_spin = QSpinBox()
        self.arc_spin.setRange(0, 100)
        self.arc_spin.setValue(0)
        self.arc_spin.setSuffix(" %")
        self.arc_spin.setAccessibleName("Manual deep-ball arc, per cent")
        self.arc_spin.setToolTip("Used only when Realistic deep-ball flight is off: higher values slow the ball past the last "
                                 "25 yards of the ceiling so it hangs longer and climbs higher (the same control as Throw Distance & Arc).")
        arc_row.addWidget(self.arc_spin)
        arc_row.addStretch(1)
        self.throw_details.content.addLayout(arc_row)
        self.throw_details.add_text("Realistic flight overrides the manual arc. The ceiling re-spaces the game's own curve: at 80, "
                                    "a 70 arm throws 41, an 85 arm 52, a 95 arm 66 (original 40 / 45 / 50 / 55).")
        g.addWidget(self.throw_details)
        self.catch_check = self._option(g, "catch_slider", "Fix Catching & Interception sliders",
                                        "Catching controls drops; Interception controls picks.",
                                        details="The catch roll is divided by twice the receiver's side's Catching slider (the menu goes to 200) "
                                                "and a defender's roll by twice the Interception slider (0 = no picks, 50 = original, 100 = double).")
        self.accel_check = self._option(g, "accel_ramp", "Gradual player acceleration",
                                        "Agility controls how quickly players reach top speed.",
                                        details="The original has no acceleration: everyone is at top speed on the first step. Players now wind up "
                                                "from 60 % to 100 % of their Speed, about 1 s at 99 Agility and 2 s at 30; standing still resets it.")
        self.kick_rules_check = self._option(g, "kick_rules", "Modern kick spots & kicking power",
                                             "Kickoff: 35 · touchback: 35 · PAT snap: 15.",
                                             details="These describe the shipped patch, not a newly verified NFL ruleset. Two-point tries stay at the 2; "
                                                     "the kick meter and kicker curves are re-spaced so a 99 leg reaches 65-69 yards; onside and safety "
                                                     "kicks are untouched; the CPU keeps its original field-goal range for fourth-down decisions.")
        self.kick_power_check = self._option(g, "kick_power", "More kicking power; keep 2004 kick spots",
                                             "The Basic preset's kicking fix: ~70-yard legs for elite kickers, original kick spots.")
        self.kickoff_alignment_check = self._option(g, "kickoff_alignment", "Dynamic kickoff alignment",
                                                    "Coverage on the receiving 40, return setup zone 35-30, two returners deep.",
                                                    badge=NOT_TESTED, needs_image=True)
        self.dynamic_kickoff_check = self._option(g, "dynamic_kickoff", "Dynamic kickoff rule (2024/2025)",
                                                  "Nobody moves until the ball comes down; landing zone; the CPU kicks to it and takes touchbacks. "
                                                  "Switches on the modern kick spots and the alignment.",
                                                  badge=NOT_TESTED, needs_image=True,
                                                  details="First contact in the landing zone then downed in the end zone puts the ball on the 20, a kick "
                                                          "straight into the end zone is a touchback to the 35, short or out is the 40; the CPU kicker aims "
                                                          "for the landing zone 90 % of the time and the CPU returner takes the touchback 90 % of the time. "
                                                          "Your own kicks and returns stay in your hands; onside and safety kicks are untouched.")
        self.overtime_check = self._option(g, "overtime", "Modern overtime rules",
                                           "Both teams get a possession; regular-season ties remain.",
                                           details="Each team is guaranteed a possession unless the kicking team scores a safety; after both have "
                                                   "possessed the leader wins or the next score wins; regular-season overtime is one 10-minute period "
                                                   "(scaled with the quarter length) and can tie; the postseason keeps playing.")
        self.penalties_check = self._option(g, "penalties", "Adjusted penalty rates (experimental)",
                                            "Estimated rates; includes the Chop Block toggle fix.", badge=NOT_TESTED,
                                            details="Seven hidden curve tables are re-knotted so the default 50 lands near NFL 2024 per-game rates (0 still "
                                                    "means none, 100 keeps the original extreme), the incidental face mask becomes 15 yards, and the Chop Block "
                                                    "On/Off toggle really works (switch it On in Penalty Settings). Rates are ESTIMATED pending a playtest.")
        self.kick_laces_check = self._option(g, "kick_laces", "Laces face the posts on kicks",
                                             "On field goals and PATs the held ball is turned so the laces face the posts.", badge=NOT_TESTED)
        self.uniform_choice_check = self._option(g, "uniform_choice", "Choose home/away jerseys at any stadium",
                                                 "Up/down past the last era on Controller Assign or Team Select flips that side's colour "
                                                 "(era cycling continues after the flip).", badge=NOT_TESTED)
        mode_row = QHBoxLayout()
        mode_row.addSpacing(30)
        mode_row.addWidget(QLabel("Jersey mode"))
        self.uniform_choice_mode = QComboBox()
        self.uniform_choice_mode.setAccessibleName("Jersey choice mode")
        self.uniform_choice_mode.addItem("Choose either jersey", "choice")
        self.uniform_choice_mode.addItem("Home dark / away white", "rule")
        self.uniform_choice_mode.setToolTip("Choose either jersey keeps the original default and adds the flip; Home dark / away white "
                                            "applies one rule to every game (no Cowboys exception). Leave the box unticked for the original behavior.")
        mode_row.addWidget(self.uniform_choice_mode)
        mode_row.addStretch(1)
        g.addLayout(mode_row)
        ol.addWidget(gameplay)

        # ---- Franchise
        franchise = QGroupBox("Franchise")
        f = QVBoxLayout(franchise)
        self.draft_check = self._option(f, "draft_ai", "Smarter Franchise drafts & free agency",
                                        "Changes CPU decisions; Fantasy Draft is separate.",
                                        details="The pick is the prospect with the best edge over his own position's class average, times real "
                                                "positional value, plus the team's need order and a little noise; CPU free-agent targets are scored the same way.")
        self.returner_check = self._option(f, "returner_fix", "Fix CPU kick & punt returners",
                                           "Changes automatic depth-chart selection.",
                                           details="The original stores a punt-return score as the roster slot, so the punt returner is whoever sits in "
                                                   "slot 0 (often a QB). Returners are now tracked by player, starters stay off the units unless nobody "
                                                   "else is eligible, and only WR, CB, S, RB and FB can return.")
        self.progression_check = self._option(f, "progression", "Change player growth & decline",
                                              "Growth over years 1-5, harder decline after years 9-12; more stars and busts.",
                                              details="The ten aging-curve tables grow by rating family and decline harder after year 9-12 (speed first); each "
                                                      "position's archetype mix is widened. Draft-day ratings are unchanged.")
        self.team_column_check = self._option(f, "team_column", "Show TEAM in Player Card season stats",
                                              "Which team each season was played for.",
                                              details="Seasons that ended before this change was in the save, the folded \"pre\" row and the Total row read "
                                                      "\"--\" until their next rollover. Franchise saves stay loadable either way.")
        self.team_history_check = self._option(f, "team_history", "Past teams in Player Card stats",
                                               "New franchises only; missing seasons use the player's 2004 team.",
                                               badge="New franchises only", needs_image=True,
                                               details="Writes the real club of every past season the roster carries stats for (built-in nflverse data, "
                                                       "CC-BY-4.0). Seasons the data does not cover are filled with the player's own 2004 club; only the 2004 "
                                                       "free agents still read \"--\". A CSV under Custom data replaces the built-in data.")
        self.career_stats_check = self._option(f, "career_stats", "Career stats from CSV",
                                               "Real per-season counters for the roster's past seasons, from a CSV you supply.",
                                               badge="New franchises only", needs_image=True,
                                               details="Columns and identity pins are in docs/mod_editor/career_stats.md; export the roster's own counters "
                                                       "first with tools/nfl2k5_career_stats.py. A season the CSV does not name is left as the roster has it. "
                                                       "CSV only (.xlsx is not read).")
        self.career_row = QWidget()
        career_row = QHBoxLayout(self.career_row)
        career_row.setContentsMargins(30, 0, 0, 0)
        career_row.addWidget(QLabel("Career stats CSV"))
        self.career_stats_field = QLineEdit()
        self.career_stats_field.setPlaceholderText("Choose a CSV file")
        career_row.addWidget(self.career_stats_field, 1)
        self.career_stats_button = QPushButton("Choose…")
        self.career_stats_button.clicked.connect(self._choose_career_stats)
        career_row.addWidget(self.career_stats_button)
        self.career_row.hide()
        f.addWidget(self.career_row)
        self.prospect_names_check = self._option(f, "prospect_names", "Modern draft-prospect names",
                                                 "New franchises only; some new surnames are announced by number.",
                                                 badge="New franchises only", needs_image=True,
                                                 details="The 485 first names and 485 surnames the game draws for rookies and free agents become the most "
                                                         "common names of 2015-2025 NFL players; the 433 surnames the announcer has recorded keep their "
                                                         "call-out. A CSV under Custom data replaces the built-in list (columns first,last; 485 rows).")
        self.season_check = self._option(f, "season_2026", "2026 Franchise season",
                                         "2026 schedule, 17 games, 14-team playoffs; this does not update the player roster.",
                                         needs_image=True,
                                         details="Real 2026 schedule with the 3-game preseason, 17 games over 18 weeks with one bye, 2026 dates and rookie "
                                                 "birth years.")
        self.position_row_check = self._option(f, "position_row", "Change position in Edit Player",
                                               "In-game: use Depth Chart → Auto afterward.", badge=NOT_TESTED,
                                               details="The Position row (the game's own picker, 17 positions, ratings kept, overall recomputed) sits "
                                                       "after Last Name on the first page of Edit Player, in roster mode and in Franchise.")
        self.probowl_order_check = self._option(f, "probowl_order", "Pro Bowl Votes: offense, defense, kickers",
                                                "The tabs run offence, defence, then K and P.", badge=NOT_TESTED)
        self.franchise_practice_check = self._option(f, "franchise_practice", "Free Practice inside Franchise",
                                                     "A Practice row on the Coach's Desk: your first team against itself, no stats or injuries.",
                                                     badge=NOT_TESTED)
        self.seven_on_seven_check = self._option(f, "seven_on_seven", "7-on-7 practice",
                                                 "Practice Type 7-On-7 with 7-on-7 sets in the practice playbook.",
                                                 badge=NOT_TESTED, needs_image=True)
        ol.addWidget(franchise)

        # ---- Rosters & positions
        rosters = QGroupBox(tab_title("Rosters & positions"))
        r = QVBoxLayout(rosters)
        self.edge_check = self._option(r, "edge_rename", "Call defensive ends EDGE",
                                       "Rosters, depth charts, the draft, the formation editor and the scorebug legend say EDGE.")
        self.scheme_labels_check = self._option(r, "scheme_labels", "Use scheme-specific depth-chart names",
                                                "4-3: SAM, MIKE, WILL; 3-4: EDGE, MIKE, WILL, NT.")
        self.position_pools_check = self._option(r, "position_pools", "Merge EDGE, LB & interior position groups",
                                                 "Changes roster positions and playbook assignments; includes scheme-specific names.",
                                                 needs_image=True)
        self.depth_roles_check = self._option(r, "depth_roles", "X / Z / SLOT receivers and nickel / dime corners",
                                              "Changes who lines up in every playbook, not how they play.",
                                              badge=NOT_TESTED, needs_image=True,
                                              details="The innermost receiver of a three-wide set becomes your third receiver (SLOT, with X and Z outside) "
                                                      "and nickel / dime sets use your third and fourth corners inside. Groups whose formations disagree, "
                                                      "bunch sets and special teams keep their original assignments; the build report lists them.")
        self.depth_chart_rows_check = self._option(r, "depth_chart_rows", "SLOT, NICKEL and DIME rows on the depth chart",
                                                   "Switches on the merged position groups and the playbook roles when the disc lacks them.",
                                                   badge=NOT_TESTED, needs_image=True,
                                                   details="Thirteen depth-chart rows per unit instead of eleven: a SLOT row on offence, NICKEL CORNER and "
                                                           "DIME CORNER rows on both defences, LWR / RWR shown as X / Z. The new rows are views onto your "
                                                           "receiver and corner lists.")
        self.roster_edits_check = self._option(r, "roster_edits", "Include exported ★ Rosters edits",
                                               "Export roster edits on ★ Rosters, then choose that JSON file here.", needs_image=True,
                                               details="Applies a roster-edits snapshot written by ★ Rosters. It runs last of the roster passes and writes only "
                                                       "named record fields and shared name strings, so star tags, team history, prospect names and the "
                                                       "position groups all survive.")
        self.edits_row = QWidget()
        edits_row = QHBoxLayout(self.edits_row)
        edits_row.setContentsMargins(30, 0, 0, 0)
        edits_row.addWidget(QLabel("Roster edits JSON"))
        self.roster_edits_field = QLineEdit()
        self.roster_edits_field.setPlaceholderText("Export roster edits on ★ Rosters or choose a JSON file")
        edits_row.addWidget(self.roster_edits_field, 1)
        self.roster_edits_button = QPushButton("Choose…")
        self.roster_edits_button.clicked.connect(self._choose_roster_edits)
        edits_row.addWidget(self.roster_edits_button)
        self.edits_row.hide()
        r.addWidget(self.edits_row)
        self.roster_edits_status = QLabel("")
        self.roster_edits_status.setObjectName("throwMuted")
        self.roster_edits_status.setWordWrap(True)
        self.roster_edits_status.hide()
        r.addWidget(self.roster_edits_status)
        self.player_star_check = self._option(r, "player_star", "Show a star under selected players",
                                             "At most 9 stars at once; not yet tested in-game.", badge=NOT_TESTED,
                                             details="The game's own controller star follows every player you select. With nobody selected nothing "
                                                     "changes on screen. The same routine gates the on-field name/number indicator, so a selected player "
                                                     "gets that too when Player Indicator Text is on. The tags reach franchises created from the copy.")
        self.star_players_label = QLabel("")
        self.star_players_label.setObjectName("throwMuted")
        self.star_players_label.setWordWrap(True)
        self.star_players_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        r.addWidget(self.star_players_label)
        ol.addWidget(rosters)

        # ---- Presentation
        pres = QGroupBox("Presentation")
        pl = QVBoxLayout(pres)
        self.scorebug_check = self._option(pl, "scorebug", "Modern ESPN scorebar",
                                           "One bar at the bottom centre that never swaps sides and stays up during plays.",
                                           needs_image=True,
                                           details="Also repaints the frame atlas and the ESPN strip, lifts the kick meter and turns the line-up strip off; "
                                                   "the mesh lives in the field resource pack, which is why the full disc is needed.")
        self.camera_check = self._option(pl, "camera", "Make Standard camera look like Far",
                                         "The Standard preset takes Far's look-at, lens and offset; Far itself is untouched.")
        self.widescreen_check = self._option(pl, "widescreen", "Widescreen 16:9",
                                             "Set xemu Display aspect ratio to 16x9.", badge=NOT_TESTED,
                                             details="Hor+: the 3D view widens, HUD and menus keep their 4:3 sizing (pillarboxed). "
                                                     "xemu: Settings -> Display -> aspect ratio, or [display.ui] aspect_ratio in xemu.toml.")
        ol.addWidget(pres)

        # ---- Custom data (optional overrides) and the advanced inputs
        self.custom_details = Details("Custom data (optional spreadsheets)")
        history_row = QHBoxLayout()
        history_row.addWidget(QLabel("Team history CSV (optional)"))
        self.team_history_field = QLineEdit()
        self.team_history_field.setPlaceholderText("last_name,first_name,birth_date,season,team — replaces the built-in data")
        history_row.addWidget(self.team_history_field, 1)
        self.team_history_button = QPushButton("Choose…")
        self.team_history_button.clicked.connect(self._choose_team_history)
        history_row.addWidget(self.team_history_button)
        self.custom_details.content.addLayout(history_row)
        names_row = QHBoxLayout()
        names_row.addWidget(QLabel("Prospect names CSV (optional)"))
        self.prospect_names_field = QLineEdit()
        self.prospect_names_field.setPlaceholderText("first,last (485 rows) — replaces the built-in list")
        names_row.addWidget(self.prospect_names_field, 1)
        self.prospect_names_button = QPushButton("Choose…")
        self.prospect_names_button.clicked.connect(self._choose_prospect_names)
        names_row.addWidget(self.prospect_names_button)
        self.custom_details.content.addLayout(names_row)
        ol.addWidget(self.custom_details)

        self.advanced_details = Details("More inputs (commentary, playbook packs, description)")
        adv = self.advanced_details.content
        self.commentary_box = QGroupBox("Commentary replacements (0)")
        cb = QVBoxLayout(self.commentary_box)
        self.commentary_list = QListWidget()
        self.commentary_list.setAccessibleName("Commentary replacements")
        self.commentary_list.setMaximumHeight(90)
        cb.addWidget(self.commentary_list)
        crow = QHBoxLayout()
        crow.addWidget(QLabel("Line ID"))
        self.commentary_stream_field = QLineEdit()
        self.commentary_stream_field.setPlaceholderText("bank:index, e.g. cutsceneaudio:12 (Presentation ▸ Commentary lists them)")
        crow.addWidget(self.commentary_stream_field, 1)
        crow.addWidget(QLabel("Replacement WAV"))
        self.commentary_wav_field = QLineEdit()
        self.commentary_wav_field.setPlaceholderText("A WAV or other audio file")
        crow.addWidget(self.commentary_wav_field, 1)
        self.commentary_wav_button = QPushButton("Choose…")
        self.commentary_wav_button.clicked.connect(self._choose_commentary_wav)
        crow.addWidget(self.commentary_wav_button)
        self.commentary_add_button = QPushButton("Add line…")
        self.commentary_add_button.clicked.connect(self._add_commentary_line)
        crow.addWidget(self.commentary_add_button)
        self.commentary_remove_button = QPushButton("Remove selected")
        self.commentary_remove_button.clicked.connect(self._remove_commentary_line)
        crow.addWidget(self.commentary_remove_button)
        cb.addLayout(crow)
        self.commentary_label = QLabel("Each line is cut to its slot's length (a shorter recording is padded with silence). "
                                       "Presentation ▸ Commentary previews the fit; this list is a direct input to the build.")
        self.commentary_label.setObjectName("throwMuted")
        self.commentary_label.setWordWrap(True)
        cb.addWidget(self.commentary_label)
        adv.addWidget(self.commentary_box)
        packs_box = QGroupBox("Playbook packs (.2k5book)")
        pb = QVBoxLayout(packs_box)
        self.packs_list = QListWidget()
        self.packs_list.setAccessibleName("Playbook packs")
        self.packs_list.setMaximumHeight(80)
        pb.addWidget(self.packs_list)
        prow = QHBoxLayout()
        self.packs_add_button = QPushButton("Add pack…")
        self.packs_add_button.clicked.connect(self._add_playbook_pack)
        prow.addWidget(self.packs_add_button)
        self.packs_remove_button = QPushButton("Remove selected")
        self.packs_remove_button.clicked.connect(self._remove_playbook_pack)
        prow.addWidget(self.packs_remove_button)
        prow.addStretch(1)
        pb.addLayout(prow)
        packs_note = QLabel("Installed in order into the copy's team books; full disc required. "
                            "Playbooks & Plays ▸ Install Playbook Pack… previews what a pack replaces.")
        packs_note.setObjectName("throwMuted")
        packs_note.setWordWrap(True)
        pb.addWidget(packs_note)
        adv.addWidget(packs_box)
        desc_box = QGroupBox("Build description (optional)")
        db = QGridLayout(desc_box)
        db.addWidget(QLabel("Mod name"), 0, 0)
        self.name_field = QLineEdit()
        self.name_field.setPlaceholderText("Recorded in the build receipt and the mod file; no effect on gameplay")
        db.addWidget(self.name_field, 0, 1)
        db.addWidget(QLabel("Author"), 1, 0)
        self.author_field = QLineEdit()
        db.addWidget(self.author_field, 1, 1)
        db.addWidget(QLabel("Notes"), 2, 0)
        self.notes_field = QPlainTextEdit()
        self.notes_field.setMaximumHeight(56)
        db.addWidget(self.notes_field, 2, 1)
        adv.addWidget(desc_box)
        ol.addWidget(self.advanced_details)
        root.addWidget(options)
        self.career_stats_check.toggled.connect(self.career_row.setVisible)
        self.roster_edits_check.toggled.connect(self.edits_row.setVisible)
        self.roster_edits_check.toggled.connect(lambda on: self.roster_edits_status.setVisible(on and bool(self.roster_edits_status.text())))
        self.uniform_choice_mode.setEnabled(False)
        self.uniform_choice_check.toggled.connect(self.uniform_choice_mode.setEnabled)
        self.kick_rules_check.toggled.connect(lambda on: on and self.kick_power_check.setChecked(False))
        self.kick_power_check.toggled.connect(lambda on: on and self.kick_rules_check.setChecked(False))
        self.set_star_players([])

        root.addStretch(1)

        # Every input feeds one refresh (M03): a lone camera tick enables the button, and a
        # ticked option whose required file is missing names that file instead of vanishing.
        for box in self.findChildren(QCheckBox):
            box.toggled.connect(lambda _c: self._refresh())
        self.ceiling_spin.valueChanged.connect(lambda _v: self._refresh())
        for field in (self.team_history_field, self.career_stats_field, self.prospect_names_field, self.roster_edits_field):
            field.textChanged.connect(lambda _t: self._refresh())
        self._refresh()

    def _option(self, layout: QVBoxLayout, key: str, label: str, helper: str = "", *, badge: str = "",
                needs_image: bool = False, details: str = "") -> QCheckBox:
        """One change: a real check box, a helper line, a qualifier badge and an optional Details."""

        row = QWidget()
        rl = QVBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 2)
        rl.setSpacing(1)
        head = QHBoxLayout()
        head.setSpacing(8)
        box = QCheckBox(label)
        box.setAccessibleDescription(helper)
        head.addWidget(box)
        badge_label = QLabel(badge)
        badge_label.setObjectName("optionBadge")
        badge_label.setVisible(bool(badge))
        head.addWidget(badge_label)
        head.addStretch(1)
        rl.addLayout(head)
        helper_label = QLabel(helper)
        helper_label.setObjectName("throwMuted")
        helper_label.setWordWrap(True)
        helper_label.setIndent(30)
        helper_label.setVisible(bool(helper))
        rl.addWidget(helper_label)
        if details:
            more = Details("Details")
            more.add_text(details)
            more.setContentsMargins(30, 0, 0, 0)
            rl.addWidget(more)
        layout.addWidget(row)
        self._helpers[key] = helper_label
        self._badges[key] = badge_label
        self._static_badges[key] = badge
        if needs_image:
            self._needs_image.add(key)
        return box

    def _set_badge(self, key: str, text: str) -> None:
        badge = self._badges.get(key)
        if badge is not None:
            badge.setText(text)
            badge.setVisible(bool(text))

    # ------------------------------------------------------------- state
    def begin_reading(self, source: Path | str) -> None:
        """The shell is inspecting the open disc; say so until the state arrives."""

        self._reading = True
        self.source_field.setText(str(source))
        self.source_status.setText("Reading disc…")
        self._refresh()

    def reading_failed(self, message: str) -> None:
        self._reading = False
        self.source_status.setText(plain_failure("read this disc", message))
        self._refresh()

    def _user_target(self) -> None:
        self._target_generated = False
        self._refresh()

    def suggest_target(self) -> None:
        """A distinct, non-existing copy name beside the source when no target was chosen (BS-09)."""

        source = self.source_field.text().strip()
        if not source or not tt.is_disc_image(source):
            return
        if self.target_field.text().strip() and not self._target_generated:
            return
        self.target_field.setText(suggest_copy_name(source, suffix="modded"))
        self._target_generated = True

    def apply_state(self, state: dict[str, object]) -> None:
        """Populate from mod_build.inspect output (also used by tests)."""

        self._state = state
        self._reading = False
        self.source_field.setText(str(state.get("path", "")))
        is_image = state.get("container") == "xiso"
        source_caption, target_caption = source_captions(is_image)
        self.source_caption.setText(source_caption)
        self.target_caption.setText(target_caption)
        bits = []
        settings = state.get("throw")
        if isinstance(settings, tt.TuningSettings):
            bits.append(f"throw ceiling {settings.max_deep_yards:g} yd" + (", realistic flight" if settings.realistic_flight else "") + (", arc by distance" if getattr(settings, 'arc_by_distance', False) else ""))
        for key, label in (("catch_slider", "catch/INT sliders"), ("accel_ramp", "acceleration ramp"),
                           ("draft_ai", "draft AI"), ("returner_fix", "returner fix"), ("progression", "progression"), ("team_column", "TEAM column"), ("team_history", "team history"), ("career_stats", "career stats"), ("prospect_names", "prospect names"),
                           ("kick_rules", "kick rules"), ("kick_power", "kick power"), ("kickoff_alignment", "kickoff line-up"), ("dynamic_kickoff", "dynamic kickoff"), ("overtime", "overtime"), ("season_2026", "2026 season"), ("position_row", "Position row"), ("probowl_order", "Pro Bowl order"), ("penalties", "penalties"), ("uniform_choice", "jersey choice"), ("kick_laces", "kick laces"), ("franchise_practice", "Franchise practice"), ("seven_on_seven", "7-on-7 practice"),
                           ("player_star", "star decal"), ("player_tags", "star tags"), ("roster_edits", "roster edits"),
                           ("edge_rename", "EDGE rename"), ("scheme_labels", "scheme labels"), ("position_pools", "one-pool positions"), ("depth_roles", "depth roles"), ("depth_chart_rows", "depth-chart rows"),
                           ("camera", "camera"), ("widescreen", "widescreen"),
                           ("scorebug", "ESPN scorebug")):
            bits.append(f"{label}: {state.get(key)}")
        # The disc's identity comes first: a repacked or pre-modded image decides whether Build
        # can work at all, and the user should read that before pressing the button, not after a
        # step refuses 40 minutes in.  Then what is already on the disc, in the same short words
        # the option list uses (BS-02).
        head = ("Disc read." if is_image else "Executable (default.xbe) read.")
        identity = str(state.get("disc_identity_line") or "")
        if identity:
            head += " " + identity.rstrip(".") + "."
        applied = [f"{label}: applied" for key, label in (
            ("catch_slider", "catch/INT sliders"), ("accel_ramp", "acceleration ramp"), ("draft_ai", "draft AI"),
            ("returner_fix", "returner fix"), ("progression", "progression"), ("team_column", "TEAM column"),
            ("team_history", "team history"), ("career_stats", "career stats"), ("prospect_names", "prospect names"),
            ("kick_rules", "kick rules"), ("kick_power", "kick power"), ("kickoff_alignment", "kickoff line-up"),
            ("dynamic_kickoff", "dynamic kickoff"), ("overtime", "overtime"), ("season_2026", "2026 season"),
            ("position_row", "Position row"), ("probowl_order", "Pro Bowl order"), ("penalties", "penalties"),
            ("uniform_choice", "jersey choice"), ("kick_laces", "kick laces"), ("franchise_practice", "Franchise practice"),
            ("seven_on_seven", "7-on-7 practice"), ("player_star", "star decal"), ("player_tags", "star tags"),
            ("roster_edits", "roster edits"), ("edge_rename", "EDGE rename"), ("scheme_labels", "scheme labels"),
            ("position_pools", "one-pool positions"), ("depth_roles", "depth roles"), ("depth_chart_rows", "depth-chart rows"),
            ("camera", "camera"), ("widescreen", "widescreen"), ("scorebug", "ESPN scorebug"))
            if state.get(key) == "applied"]
        foreign = [key.replace("_", " ") for key in mod_build.BuildPlan.__dataclass_fields__
                   if state.get(key) == "foreign"]
        settings = state.get("throw")
        if isinstance(settings, tt.TuningSettings) and settings.max_deep_yards != tt.RETAIL_MAX_DEEP_YARDS:
            applied.insert(0, f"throw ceiling {settings.max_deep_yards:g} yd: applied")
        parts = [head]
        parts.append("Already on this disc: " + ", ".join(applied) + "." if applied
                     else "No recognized patches found; everything the options list is original.")
        if foreign:
            parts.append("Not recognized (changed by another tool): " + ", ".join(foreign) + ".")
        self.source_status.setText(" ".join(parts))
        self.source_status.setToolTip("Full read-back: " + "; ".join(bits))
        # a patch already applied cannot be re-applied; a foreign site disables the toggle; the
        # badge next to the row says which (never a ticked box pretending to mean "installed")
        def gate(box: QCheckBox, key: str, needs_image: bool = False, module: str | None = None) -> None:
            value = str(state.get(key))
            available = self._available.get(module or key, True)
            box.setEnabled(available and value == "retail" and (is_image or not needs_image))
            box.setChecked(False)
            if not available:
                box.setToolTip("Not available in this release.")
                self._set_badge(key, "Not available in this release")
            elif value == "applied":
                box.setToolTip("Already installed on this source.")
                self._set_badge(key, "Already installed")
            elif value == "foreign":
                box.setToolTip("Not recognised: the bytes at this change's sites are neither retail nor this patch "
                               "(changed by another tool), so it can't be added here.")
                self._set_badge(key, "Unrecognized source data")
            elif needs_image and not is_image:
                box.setToolTip("Full disc required (not a bare default.xbe).")
                self._set_badge(key, "Full disc required")
            else:
                box.setToolTip("")
                self._set_badge(key, self._static_badges.get(key, ""))
        gate(self.catch_check, "catch_slider")
        gate(self.accel_check, "accel_ramp")
        gate(self.draft_check, "draft_ai")
        gate(self.returner_check, "returner_fix")
        gate(self.progression_check, "progression")
        gate(self.team_column_check, "team_column")
        gate(self.team_history_check, "team_history", needs_image=True)
        gate(self.career_stats_check, "career_stats", needs_image=True)
        gate(self.prospect_names_check, "prospect_names", needs_image=True)
        # an already-edited roster can take more edits: gate on availability and the container only
        self.roster_edits_check.setEnabled(self._available.get("roster_edits", True) and is_image)
        self.roster_edits_check.setChecked(False)
        self.roster_edits_check.setToolTip("" if is_image else "Full disc required (not a bare default.xbe).")
        self._set_badge("roster_edits", "" if is_image else "Full disc required")
        gate(self.kick_rules_check, "kick_rules")
        gate(self.kick_power_check, "kick_power", module="kick_rules")
        gate(self.kickoff_alignment_check, "kickoff_alignment", needs_image=True)
        gate(self.dynamic_kickoff_check, "dynamic_kickoff", needs_image=True)
        gate(self.season_check, "season_2026", needs_image=True)
        gate(self.overtime_check, "overtime")
        gate(self.position_row_check, "position_row")
        gate(self.probowl_order_check, "probowl_order")
        gate(self.penalties_check, "penalties")
        gate(self.uniform_choice_check, "uniform_choice")
        gate(self.kick_laces_check, "kick_laces")
        gate(self.franchise_practice_check, "franchise_practice")
        gate(self.seven_on_seven_check, "seven_on_seven", needs_image=True)
        gate(self.player_star_check, "player_star")
        gate(self.edge_check, "edge_rename")
        gate(self.scheme_labels_check, "scheme_labels")
        gate(self.position_pools_check, "position_pools", needs_image=True)
        gate(self.depth_roles_check, "depth_roles", needs_image=True)
        gate(self.depth_chart_rows_check, "depth_chart_rows", needs_image=True)
        if any(state.get(k) == "foreign" for k in ("position_pools", "scheme_labels", "depth_roles")):
            self.depth_chart_rows_check.setEnabled(False)
            self.depth_chart_rows_check.setToolTip("Not recognised: something these rows depend on (position groups, scheme names or playbook roles) "
                                                   "is neither retail nor this patch, so they can't be added here.")
            self._set_badge("depth_chart_rows", "Unrecognized source data")
        self.packs_add_button.setEnabled(is_image and self._available.get("playbook_packs", True))
        self.packs_add_button.setToolTip("" if is_image else "Full disc required.")
        gate(self.scorebug_check, "scorebug", needs_image=True)
        gate(self.camera_check, "camera")
        gate(self.widescreen_check, "widescreen")
        self.throw_check.setEnabled(True)
        self.suggest_target()
        self._refresh()
        pending, self.pending_preset = self.pending_preset, None
        if pending:
            self.apply_preset_if_fresh(pending)

    def apply_preset_if_fresh(self, name: str) -> bool:
        """Tick a preset only when nothing is ticked yet; customised choices stay (BS-15)."""

        if self._state is None:
            self.pending_preset = name
            return False
        if any(box.isChecked() for box in self._toggle_boxes()):
            self.preset_note.setText("Your current choices were kept; press a preset button to replace them.")
            return False
        self.apply_preset(name)
        self.preset_note.setText(f"{mod_build.PRESET_TITLES.get(name, name)} selected; review changes below. "
                                 + self.preset_note.text())
        return True

    def _toggle_boxes(self) -> tuple[QCheckBox, ...]:
        return tuple(box for box in self.findChildren(QCheckBox)
                     if box not in (self.realistic_check, self.arc_by_distance_check))

    def apply_preset(self, name: str) -> dict[str, list[str]]:
        """Tick the preset's toggles (only those the source can still take); returns what was skipped."""

        values = mod_build.PRESETS[name]
        boxes = {
            "throw": self.throw_check, "catch_slider": self.catch_check, "accel_ramp": self.accel_check,
            "draft_ai": self.draft_check, "returner_fix": self.returner_check, "progression": self.progression_check,
            "edge_rename": self.edge_check, "scorebug": self.scorebug_check, "scheme_labels": self.scheme_labels_check,
            "camera": self.camera_check, "kick_rules": self.kick_rules_check, "kick_power": self.kick_power_check,
            "position_pools": self.position_pools_check,
            "depth_roles": self.depth_roles_check,
            "depth_chart_rows": self.depth_chart_rows_check,
            "kickoff_alignment": self.kickoff_alignment_check,
            "dynamic_kickoff": self.dynamic_kickoff_check,
            "season_2026": self.season_check, "widescreen": self.widescreen_check, "overtime": self.overtime_check,
            "team_column": self.team_column_check, "team_history": self.team_history_check, "career_stats": self.career_stats_check,
            "prospect_names": self.prospect_names_check,
            "seven_on_seven": self.seven_on_seven_check, "position_row": self.position_row_check, "probowl_order": self.probowl_order_check,
            "penalties": self.penalties_check,
            "uniform_choice": self.uniform_choice_check,
            "kick_laces": self.kick_laces_check,
            "franchise_practice": self.franchise_practice_check,
            "player_star": self.player_star_check,
            "realistic_flight": self.realistic_check, "arc_by_distance": self.arc_by_distance_check,
        }
        applied, skipped = [], []
        if "max_deep_yards" in values:
            self.ceiling_spin.setValue(int(round(float(values["max_deep_yards"]))))
        for key, box in boxes.items():
            if key not in values:
                continue
            want = bool(values[key])
            if want and not box.isEnabled() and key not in ("realistic_flight", "arc_by_distance"):
                skipped.append(key)
                continue
            box.setChecked(want)
            if want:
                applied.append(key)
        self._refresh()
        title = PRESET_LABELS.get(name, name)
        tested = ("" if name == "softdrink_basic"
                  else " Includes experimental changes not yet tested in-game.")
        if skipped:
            reasons = "; ".join(f"{self._short_label(key)} ({self._skip_reason(key)})" for key in skipped)
            self.preset_note.setText(f"{title} preset: ticked {len(applied)} changes; not available on this source: "
                                     f"{reasons}.{tested} Untick anything you do not want, then Make my disc.")
        else:
            self.preset_note.setText(f"{title} preset: ticked {len(applied)} changes.{tested} "
                                     "Untick anything you do not want, then Make my disc.")
        return {"applied": applied, "skipped": skipped}

    def _short_label(self, key: str) -> str:
        box = self._boxes().get(key)
        return box.text().replace("&&", "&") if box is not None else key

    def _skip_reason(self, key: str) -> str:
        state = str((self._state or {}).get(key))
        if not self._available.get(key, True):
            return "not available in this release"
        if state == "applied":
            return "already installed"
        if state == "foreign":
            return "unrecognized source data"
        return "full disc required"

    def _boxes(self) -> dict[str, QCheckBox]:
        return {
            "throw": self.throw_check, "catch_slider": self.catch_check, "accel_ramp": self.accel_check,
            "draft_ai": self.draft_check, "returner_fix": self.returner_check, "progression": self.progression_check,
            "edge_rename": self.edge_check, "scorebug": self.scorebug_check, "scheme_labels": self.scheme_labels_check,
            "camera": self.camera_check, "kick_rules": self.kick_rules_check, "kick_power": self.kick_power_check,
            "position_pools": self.position_pools_check, "depth_roles": self.depth_roles_check,
            "depth_chart_rows": self.depth_chart_rows_check, "kickoff_alignment": self.kickoff_alignment_check,
            "dynamic_kickoff": self.dynamic_kickoff_check, "season_2026": self.season_check,
            "widescreen": self.widescreen_check, "overtime": self.overtime_check, "team_column": self.team_column_check,
            "team_history": self.team_history_check, "career_stats": self.career_stats_check,
            "prospect_names": self.prospect_names_check, "seven_on_seven": self.seven_on_seven_check,
            "position_row": self.position_row_check, "probowl_order": self.probowl_order_check,
            "penalties": self.penalties_check, "uniform_choice": self.uniform_choice_check,
            "kick_laces": self.kick_laces_check, "franchise_practice": self.franchise_practice_check,
            "player_star": self.player_star_check, "roster_edits": self.roster_edits_check,
            "realistic_flight": self.realistic_check, "arc_by_distance": self.arc_by_distance_check,
        }

    def set_star_players(self, tags: list[str], names: list[str] | None = None) -> None:
        """The ★ Star ticks from Names, Numbers & Faces: the players the star follows."""

        self.star_players = [str(tag) for tag in tags]
        self._star_names = list(names or self.star_players)
        self._refresh_star_players_label()
        self._refresh()

    def _refresh_star_players_label(self) -> None:
        route = "Choose ★ Star under Names, Numbers & Faces → Names & Numbers → Current Roster Players."
        star_on = self.player_star_check.isChecked()
        installed = str((self._state or {}).get("player_star")) == "applied"
        names = getattr(self, "_star_names", [])
        if not self.star_players:
            text = "Selected star players (0): none selected. " + route
        else:
            over = (f" The game draws at most {player_star.STAR_LIST_LIMIT} at once."
                    if len(self.star_players) > player_star.STAR_LIST_LIMIT else "")
            text = (f"Selected star players ({len(self.star_players)}): {', '.join(names[:8])}"
                    + (", …" if len(names) > 8 else "") + f".{over} Full disc required.")
            if not star_on and not installed:
                text += " Player tags are selected, but the star display is off."
        self.star_players_label.setText(text)

    def plan(self) -> mod_build.BuildPlan:
        plan = mod_build.BuildPlan(
            source=self.source_field.text(), target=self.target_field.text(),
            overwrite=Path(self.target_field.text()).exists() if self.target_field.text() else False,
            throw=self.throw_check.isChecked(), max_deep_yards=float(self.ceiling_spin.value()),
            arc=float(self.arc_spin.value()) / 100.0,
            realistic_flight=self.realistic_check.isChecked(),
            arc_by_distance=self.arc_by_distance_check.isChecked(),
            catch_slider=self.catch_check.isChecked(), accel_ramp=self.accel_check.isChecked(),
            draft_ai=self.draft_check.isChecked(), edge_rename=self.edge_check.isChecked(),
            returner_fix=self.returner_check.isChecked(), progression=self.progression_check.isChecked(),
            scheme_labels=self.scheme_labels_check.isChecked(), camera=self.camera_check.isChecked(),
            kick_rules=self.kick_rules_check.isChecked(), kick_power=self.kick_power_check.isChecked(),
            position_pools=self.position_pools_check.isChecked(),
            depth_roles=self.depth_roles_check.isChecked(),
            depth_chart_rows=self.depth_chart_rows_check.isChecked(),
            kickoff_alignment=self.kickoff_alignment_check.isChecked(),
            dynamic_kickoff=self.dynamic_kickoff_check.isChecked(),
            season_2026=self.season_check.isChecked(), widescreen=self.widescreen_check.isChecked(),
            overtime=self.overtime_check.isChecked(), team_column=self.team_column_check.isChecked(), seven_on_seven=self.seven_on_seven_check.isChecked(),
            position_row=self.position_row_check.isChecked(), probowl_order=self.probowl_order_check.isChecked(),
            penalties=("nfl" if self.penalties_check.isChecked() else ""),
            uniform_choice=(str(self.uniform_choice_mode.currentData() or "choice") if self.uniform_choice_check.isChecked() else ""),
            kick_laces=self.kick_laces_check.isChecked(),
            franchise_practice=self.franchise_practice_check.isChecked(),
            player_star=self.player_star_check.isChecked(), player_tags=list(self.star_players),
            team_history=((self.team_history_field.text().strip() or "retail") if self.team_history_check.isChecked() else ""),
            career_stats=(self.career_stats_field.text().strip() if self.career_stats_check.isChecked() else ""),
            prospect_names=((self.prospect_names_field.text().strip() or "modern") if self.prospect_names_check.isChecked() else ""),
            roster_edits=(self.roster_edits_field.text().strip() if self.roster_edits_check.isChecked() else ""),
            scorebug=self.scorebug_check.isChecked(), commentary=list(self.commentary),
            playbook_packs=tuple(self.playbook_packs),
            name=self.name_field.text().strip(), author=self.author_field.text().strip(),
            notes=self.notes_field.toPlainText().strip(),
        )
        if plan.depth_chart_rows:
            state = self._state or {}
            plan.position_pools = plan.position_pools or state.get("position_pools") != "applied"
            plan.scheme_labels = plan.scheme_labels or state.get("scheme_labels") != "applied"
            plan.depth_roles = plan.depth_roles or state.get("depth_roles") != "applied"
        return plan

    def has_work(self) -> bool:
        p = self.plan()
        return bool(p.throw or p.catch_slider or p.accel_ramp or p.draft_ai or p.returner_fix or p.progression
                    or p.edge_rename or p.scorebug or p.scheme_labels or p.camera or p.kick_rules or p.kick_power or p.position_pools or p.depth_roles or p.depth_chart_rows
                    or p.kickoff_alignment or p.dynamic_kickoff or p.season_2026 or p.widescreen or p.overtime or p.team_column or p.seven_on_seven or p.team_history or p.career_stats or p.position_row or p.probowl_order or p.penalties or p.uniform_choice or p.kick_laces or p.franchise_practice or p.prospect_names or p.player_star or p.player_tags or p.roster_edits or p.commentary
                    or p.playbook_packs)

    def selected_labels(self) -> list[str]:
        """The short names of every ticked change, in page order."""

        labels = []
        for key, box in self._boxes().items():
            if key in ("realistic_flight", "arc_by_distance"):
                continue
            if box.isChecked():
                text = box.text().replace("&&", "&")
                if key == "throw":
                    text += f" ({self.ceiling_spin.value()} yd)"
                labels.append(text)
        if self.star_players:
            labels.append(f"star players ({len(self.star_players)})")
        if self.commentary:
            labels.append(f"commentary lines ({len(self.commentary)})")
        if self.playbook_packs:
            labels.append(f"playbook packs ({len(self.playbook_packs)})")
        return labels

    def blocker(self) -> str:
        """Why Make my disc is unavailable, or "" when it can run (most blocking first)."""

        if self._task is not None:
            return "Wait for the current build to finish."
        if self._reading:
            return "Reading disc…"
        source = self.source_field.text().strip()
        if not source:
            return "Open your game disc (top right), or choose a disc / default.xbe above."
        if self._state is None:
            return "Waiting for the disc to be read."
        if self.career_stats_check.isChecked() and not self.career_stats_field.text().strip():
            return "Choose a career stats CSV file."
        if self.roster_edits_check.isChecked() and not self.roster_edits_field.text().strip():
            return "Export roster edits on ★ Rosters or choose a JSON file."
        if not self.has_work():
            return "Tick at least one change, or press a preset."
        target = self.target_field.text().strip()
        if not target:
            return "Choose where to save the disc."
        try:
            same = Path(target).resolve() == Path(source).resolve()
        except OSError:
            same = target == source
        if same:
            return "Source and output are the same file. Fix: choose a different output file."
        return ""

    def _refresh(self) -> None:
        self.ceiling_spin.setEnabled(self.throw_check.isChecked())
        self.realistic_check.setEnabled(self.throw_check.isChecked())
        self.arc_by_distance_check.setEnabled(self.throw_check.isChecked())
        self.arc_spin.setEnabled(self.throw_check.isChecked() and not self.realistic_check.isChecked())
        if hasattr(self, "star_players_label"):
            self._refresh_star_players_label()
        labels = self.selected_labels()
        if labels:
            shown = ", ".join(labels[:6]) + (f" … (+{len(labels) - 6} more)" if len(labels) > 6 else "")
            self.summary_label.setText(f"Selected: {len(labels)} change{'s' if len(labels) != 1 else ''} — {shown}.")
        else:
            self.summary_label.setText("Selected: nothing yet.")
        blocker = self.blocker()
        self.build_button.setEnabled(not blocker)
        self.blocker_label.setText(blocker)
        self.build_button.setToolTip(blocker or "Copies the disc and writes the selected changes into the copy (a few minutes).")
        self.build_button.setAccessibleDescription(self.build_button.toolTip())

    # ------------------------------------------------------------ actions
    def _choose_source(self) -> None:
        chosen, _f = QFileDialog.getOpenFileName(self, "Choose your game disc (.iso) or default.xbe", str(Path.home()), SOURCE_FILTER)
        if not chosen:
            return
        try:
            self.apply_state(mod_build.inspect(Path(chosen)))
        except Exception as exc:  # noqa: BLE001
            show_operation_error(self, "read that file", str(exc))

    def _choose_roster_edits(self) -> None:
        chosen, _f = QFileDialog.getOpenFileName(self, "Choose a roster-edits document", str(Path.home()),
                                                 "Roster edits (*.json);;All files (*)")
        if chosen:
            self.set_roster_edits(chosen)

    def set_roster_edits(self, path: str) -> None:
        """★ Rosters calls this when it exports a roster-edits snapshot."""

        self.roster_edits_field.setText(path)
        self.roster_edits_check.setChecked(bool(path) and self.roster_edits_check.isEnabled())
        if path:
            self.roster_edits_status.setText(f"Snapshot: {Path(path).name}. Build uses this saved file; export again after further changes.")
        else:
            self.roster_edits_status.setText("")
        self.roster_edits_status.setVisible(bool(path) and self.roster_edits_check.isChecked())
        self._refresh()

    def mark_roster_edits_stale(self) -> None:
        """★ Rosters changed again after the export: the file on disk no longer matches."""

        path = self.roster_edits_field.text().strip()
        if path:
            self.roster_edits_status.setText(f"Snapshot: {Path(path).name} is older than the roster on ★ Rosters. "
                                             "Export roster edits again to include the latest changes.")
            self.roster_edits_status.setVisible(self.roster_edits_check.isChecked())

    def _choose_commentary_wav(self) -> None:
        chosen, _f = QFileDialog.getOpenFileName(self, "Choose the replacement recording", str(Path.home()),
                                                 "Audio (*.wav *.mp3 *.flac *.ogg *.m4a);;All files (*)")
        if chosen:
            self.commentary_wav_field.setText(chosen)

    def _add_commentary_line(self) -> None:
        stream = self.commentary_stream_field.text().strip()
        wav = self.commentary_wav_field.text().strip()
        if ":" not in stream or not wav:
            self.status_label.setText("A commentary line needs a Line ID (bank:index) and a recording.")
            return
        self.set_commentary(list(self.commentary) + [mod_build.CommentarySwap(stream, wav)])
        self.commentary_stream_field.clear()
        self.commentary_wav_field.clear()

    def _remove_commentary_line(self) -> None:
        rows = sorted({index.row() for index in self.commentary_list.selectedIndexes()}, reverse=True)
        remaining = list(self.commentary)
        for row in rows:
            if 0 <= row < len(remaining):
                del remaining[row]
        self.set_commentary(remaining)

    def set_commentary(self, swaps: list[mod_build.CommentarySwap]) -> None:
        """The commentary lines the build replaces (a direct input; also used by tests)."""

        self.commentary = list(swaps)
        self.commentary_list.clear()
        for swap in self.commentary:
            self.commentary_list.addItem(f"{swap.stream}  ←  {Path(swap.wav).name}")
        self.commentary_box.setTitle(f"Commentary replacements ({len(self.commentary)})")
        self._refresh()

    def _add_playbook_pack(self) -> None:
        chosen, _f = QFileDialog.getOpenFileNames(self, "Choose playbook packs", str(Path.home()),
                                                  "Playbook packs (*.2k5book);;All files (*)")
        if chosen:
            self.set_playbook_packs(list(self.playbook_packs) + [str(path) for path in chosen])

    def _remove_playbook_pack(self) -> None:
        rows = sorted({index.row() for index in self.packs_list.selectedIndexes()}, reverse=True)
        remaining = list(self.playbook_packs)
        for row in rows:
            if 0 <= row < len(remaining):
                del remaining[row]
        self.set_playbook_packs(remaining)

    def set_playbook_packs(self, paths: list[str]) -> None:
        """The community packs installed into the copy, in order (also used by tests)."""

        self.playbook_packs = [str(path) for path in paths]
        self.packs_list.clear()
        for path in self.playbook_packs:
            self.packs_list.addItem(Path(path).name)
        self._refresh()

    def _choose_career_stats(self) -> None:
        chosen, _f = QFileDialog.getOpenFileName(self, "Choose a career stats CSV", str(Path.home()), "CSV (*.csv);;All files (*)")
        if chosen:
            self.career_stats_field.setText(chosen)
            self.career_stats_check.setChecked(True)
            self._refresh()

    def _choose_team_history(self) -> None:
        chosen, _f = QFileDialog.getOpenFileName(self, "Choose a team history CSV", str(Path.home()), "CSV (*.csv);;All files (*)")
        if chosen:
            self.team_history_field.setText(chosen)
            self.team_history_check.setChecked(True)
            self._refresh()

    def _choose_prospect_names(self) -> None:
        chosen, _f = QFileDialog.getOpenFileName(self, "Choose a prospect names CSV", str(Path.home()), "CSV (*.csv);;All files (*)")
        if chosen:
            self.prospect_names_field.setText(chosen)
            self.prospect_names_check.setChecked(True)
            self._refresh()

    def _choose_target(self) -> None:
        is_image = bool(self.source_field.text()) and tt.is_disc_image(self.source_field.text())
        chosen, _f = QFileDialog.getSaveFileName(self, "Where should the new disc go?" if is_image else "Save the patched executable as",
                                                 "ESPN NFL 2K5 (modded).xiso.iso" if is_image else "default_modded.xbe",
                                                 IMAGE_FILTER if is_image else XBE_FILTER)
        if chosen:
            self.target_field.setText(mod_build.image_target_path(chosen) if is_image else chosen)
            self._target_generated = False
            self._refresh()

    def confirmation_text(self, plan: mod_build.BuildPlan) -> str:
        """What the user is about to make: source, output, every selected change and file."""

        is_image = tt.is_disc_image(plan.source)
        lines = [f"Source (unchanged): {plan.source}",
                 (f"Replace existing disc copy: {plan.target}" if plan.overwrite
                  else f"New {'disc' if is_image else 'executable'}: {plan.target}"),
                 "", "Changes: " + (", ".join(self.selected_labels()) or "none")]
        files = []
        if plan.team_history and plan.team_history != "retail":
            files.append(f"team history CSV: {Path(plan.team_history).name}")
        if plan.career_stats:
            files.append(f"career stats CSV: {Path(plan.career_stats).name}")
        if plan.prospect_names and plan.prospect_names != "modern":
            files.append(f"prospect names CSV: {Path(plan.prospect_names).name}")
        if plan.roster_edits:
            files.append(f"roster edits: {Path(plan.roster_edits).name}")
        if plan.playbook_packs:
            files.append(f"playbook packs: {len(plan.playbook_packs)}")
        if plan.commentary:
            files.append(f"commentary lines: {len(plan.commentary)}")
        if plan.player_tags:
            files.append(f"star players: {len(plan.player_tags)}")
        if files:
            lines.append("Files: " + "; ".join(files))
        lines += ["", "Takes a few minutes. " + XEMU_LINE]
        return "\n".join(lines)

    def _build(self) -> None:
        plan = self.plan()
        if not self.has_work() or self.blocker():
            return
        answer = QMessageBox.question(self, "Make my disc?", self.confirmation_text(plan),
                                      QMessageBox.Ok | QMessageBox.Cancel, QMessageBox.Cancel)
        if answer != QMessageBox.Ok:
            return
        task = _Task(lambda progress: mod_build.build(plan, progress))
        task.signals.progress.connect(self.progress_label.setText)
        task.signals.finished.connect(self._done)
        task.signals.failed.connect(self._failed)
        self._task = task
        self.progress_bar.show()
        self._refresh()
        self._pool.start(task)

    def _done(self, receipt: object) -> None:
        self._task = None
        self.progress_bar.hide()
        self.progress_label.setText("")
        assert isinstance(receipt, dict)
        target = str(receipt.get("target"))
        steps = ", ".join(str(s.get("step")) for s in receipt.get("steps", []))
        self.status_label.setText(f"Disc ready: {target}. Play latest disc in xemu, or open Share → Export mod file.")
        self.built.emit(dict(receipt))
        QMessageBox.information(self, "Disc ready",
                                f"{target}\n\nPlay latest disc in xemu (bottom right), or open Share → Export mod file.\n\n"
                                f"Steps written: {steps}.")
        try:
            self.apply_state(mod_build.inspect(Path(str(receipt.get("target")))))
        except Exception:  # noqa: BLE001
            pass
        else:
            # the copy just written is now the source: the next copy needs its own name,
            # never the same file (a build onto itself)
            self._target_generated = True
            self.target_field.setText("")
            self.suggest_target()
            self.source_status.setText(
                f"Build source is now: {Path(str(receipt.get('target'))).name}. " + self.source_status.text())
        self._refresh()

    def _failed(self, message: str) -> None:
        self._task = None
        self.progress_bar.hide()
        self.progress_label.setText("")
        self.status_label.setText(plain_failure("make the disc", message))
        show_operation_error(self, "make the disc", message)
        self._refresh()


__all__ = ["BuildPanel"]
