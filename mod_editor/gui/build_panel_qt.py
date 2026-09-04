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
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from mod_editor.core import mod_build
from mod_editor.core import nfl2k5_player_star as player_star
from mod_editor.core import nfl2k5_throw_tuning as tt

SOURCE_FILTER = "NFL 2K5 default.xbe or disc image (default.xbe *.xbe *.xiso *.iso *.img);;All files (*)"
IMAGE_FILTER = "Xbox disc images (*.xiso *.iso *.img);;All files (*)"
XBE_FILTER = "Xbox executables (default.xbe *.xbe);;All files (*)"


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
        intro = QLabel("Pick a source, tick what you want, write one patched copy. The source is never written. "
                       "Everything here is xemu-only (the RSA signature stays stale).")
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
        self.source_status = QLabel("Choose a default.xbe or a disc image to read what it already carries.")
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
            "QPushButton#presetButton { padding: 8px 14px; font-weight: 600; }")
        presets = QGroupBox("Start with the SOFTDRINK patch")
        pr = QVBoxLayout(presets)
        preset_row = QHBoxLayout()
        self.preset_basic_button = QPushButton("Basic: the 2004 game, just the 2K5 fixes")
        self.preset_basic_button.setToolTip("Keeps the game in 2004 and ticks only the fixes: throw ceiling 80 with realistic flight, "
                                            "Catching/Interception sliders, franchise draft and free agency AI (Rookie Report never ranks "
                                            "FB/K/P in the top 25), real returners, kicking power to ~70 yards for elite legs, the TEAM column on the Player Card. "
                                            "Retail kick spots, names, rules and presentation.")
        self.preset_basic_button.setObjectName("presetButton")
        self.preset_basic_button.clicked.connect(lambda: self.apply_preset("softdrink_basic"))
        preset_row.addWidget(self.preset_basic_button)
        self.preset_advanced_button = QPushButton("Advanced: everything modern")
        self.preset_advanced_button.setToolTip("Basic plus everything that modernises the game: DE to EDGE, modern kicking (35 / 35 / PAT 15), "
                                               "modern overtime, acceleration ramp, NFL-shaped progression, arc by distance, the persistent "
                                               "ESPN scorebug, scheme labels, one-pool positions, the Far-look camera and the 2026 franchise "
                                               "(disc images take all of it; a bare default.xbe skips the disc-only parts).")
        self.preset_advanced_button.setObjectName("presetButton")
        self.preset_advanced_button.clicked.connect(lambda: self.apply_preset("softdrink_advanced"))
        preset_row.addWidget(self.preset_advanced_button)
        self.preset_experimental_button = QPushButton("Experimental: advanced + widescreen + rough edges")
        self.preset_experimental_button.setToolTip("Advanced plus the toggles still being witnessed: widescreen hor+ 16:9 (set xemu Display "
                                                   "aspect to 16x9) and the dynamic-kickoff line-up (disc images only).")
        self.preset_experimental_button.setObjectName("presetButton")
        self.preset_experimental_button.clicked.connect(lambda: self.apply_preset("softdrink_experimental"))
        preset_row.addWidget(self.preset_experimental_button)
        preset_row.addStretch(1)
        pr.addLayout(preset_row)
        self.preset_note = QLabel("Choose a source first; a preset only ticks what that source can still take, and you can untick anything after.")
        self.preset_note.setObjectName("throwMuted")
        self.preset_note.setWordWrap(True)
        pr.addWidget(self.preset_note)
        root.addWidget(presets)

        gameplay = QGroupBox("Gameplay")
        g = QVBoxLayout(gameplay)
        throw_row = QHBoxLayout()
        self.throw_check = QCheckBox("Throw distance: ceiling at 99 arm")
        throw_row.addWidget(self.throw_check)
        self.ceiling_spin = QSpinBox()
        self.ceiling_spin.setRange(int(tt.MIN_MAX_DEEP_YARDS), int(tt.MAX_MAX_DEEP_YARDS))
        self.ceiling_spin.setValue(80)
        self.ceiling_spin.setSuffix(" yd")
        throw_row.addWidget(self.ceiling_spin)
        self.realistic_check = QCheckBox("realistic deep-ball flight")
        self.realistic_check.setChecked(True)
        throw_row.addWidget(self.realistic_check)
        self.arc_by_distance_check = QCheckBox("45-60 yd lobs hang high, 63+ flat (short game retail)")
        self.arc_by_distance_check.setToolTip("Lob speed by distance: every throw up to 40 yards keeps the retail speed table, 45 to 60 yards get the high hanging arc, 63 yards and beyond keep the flat realistic bomb (eight-point table relocated into the XBE header).")
        throw_row.addWidget(self.arc_by_distance_check)
        throw_row.addStretch(1)
        g.addLayout(throw_row)
        self.catch_check = QCheckBox("Catching slider decides drops (to 200); Interception slider decides picks")
        self.accel_check = QCheckBox("Acceleration ramp (players wind up to top speed by agility)")
        self.draft_check = QCheckBox("Realistic, unpredictable CPU drafts and free agency in franchise")
        self.returner_check = QCheckBox("Real kick and punt returners on CPU depth charts (no QB fielding punts)")
        self.progression_check = QCheckBox("NFL-shaped player development (growth, age decline, more stars and busts)")
        self.team_column_check = QCheckBox("TEAM column on the franchise Player Card's season-by-season stats (which team each season was played for)")
        self.team_history_check = QCheckBox("Real team history for the roster's past seasons on the Player Card (built-in nflverse data; every other season falls back to that player's 2004 club, so 98 % of the rows name a team; new franchises; disc images only)")
        self.team_history_check.setToolTip("Writes the real club of every past season the roster carries stats for into the roster template (one pool "
                                           "dword per season row, so the game folds the oldest seasons a little earlier). Seasons the built-in data does not "
                                           "cover are filled with the player's own 2004 club rather than left as '--'; only the retail free agents (on no 2004 "
                                           "club) still read '--'. Only franchises created from the copy see it. Give a CSV below to replace the built-in data "
                                           "(columns last_name, first_name, birth_date, season, team); a CSV row always wins over the fallback.")
        history_row = QHBoxLayout()
        history_row.addWidget(QLabel("Team history CSV (optional, replaces the built-in data)"))
        self.team_history_field = QLineEdit()
        self.team_history_field.setPlaceholderText("last_name,first_name,birth_date,season,team")
        history_row.addWidget(self.team_history_field, 1)
        self.team_history_button = QPushButton("Choose…")
        self.team_history_button.clicked.connect(self._choose_team_history)
        history_row.addWidget(self.team_history_button)
        self.prospect_names_check = QCheckBox("Modern draft-prospect names: 485 first names and 52 surnames from 2015-2025 NFL rosters in the generated-player pool (recorded surnames keep their call-outs, new ones are announced by number; new franchises; disc images only)")
        self.prospect_names_check.setToolTip("Rewrites the 485 first names and 485 surnames the game draws for rookies and free agents (the 1990 Census lists in retail) "
                                             "inside the roster template's own 13,238 bytes and hooks the generator's audio id: the 433 surnames the announcer has "
                                             "recorded stay at their index and are still called by name, the 52 replacements and every generated player with one are "
                                             "announced by number. Only franchises created from the copy see it. Give a CSV below to replace the built-in list "
                                             "(columns first,last; 485 rows; index optional; ASCII, up to 12 characters, total under 13,238 UTF-16 bytes).")
        names_row = QHBoxLayout()
        names_row.addWidget(QLabel("Prospect names CSV (optional, replaces the built-in list)"))
        self.prospect_names_field = QLineEdit()
        self.prospect_names_field.setPlaceholderText("first,last (485 rows; index optional)")
        names_row.addWidget(self.prospect_names_field, 1)
        self.prospect_names_button = QPushButton("Choose…")
        self.prospect_names_button.clicked.connect(self._choose_prospect_names)
        names_row.addWidget(self.prospect_names_button)
        self.roster_edits_check = QCheckBox("Roster edits from the ★ Rosters page (ratings, appearance, equipment, contracts, names, depth; disc images only)")
        self.roster_edits_check.setToolTip("Applies a roster-edits document (2k5_mod_studio_roster_edits/v1) written by ★ Rosters. "
                                           "It runs last of the roster passes and writes only named record fields and shared name strings, "
                                           "so the star tags, the team history, the prospect names and the position pools all survive. "
                                           "Give the JSON file below.")
        edits_row = QHBoxLayout()
        edits_row.addWidget(QLabel("Roster edits document (from ★ Rosters -> Save roster edits…)"))
        self.roster_edits_field = QLineEdit()
        self.roster_edits_field.setPlaceholderText("roster_edits.json")
        edits_row.addWidget(self.roster_edits_field, 1)
        self.roster_edits_button = QPushButton("Choose…")
        self.roster_edits_button.clicked.connect(self._choose_roster_edits)
        edits_row.addWidget(self.roster_edits_button)
        self.kick_rules_check = QCheckBox("Modern kicking: kickoff 35, touchback 35, PAT from the 15, ~70-yard legs")
        self.kick_power_check = QCheckBox("Kicking power only: ~70-yard legs for elite kickers, retail kick spots (the 2004 game)")
        self.season_check = QCheckBox("2026 franchise: real 2026 schedule + 3-game preseason, 17 games over 18 weeks, 14-team playoffs, 2026 dates and rookie birth years (disc images only)")
        self.overtime_check = QCheckBox("Modern overtime: both teams get a possession, 10 minutes with ties, playoffs play on")
        self.kickoff_alignment_check = QCheckBox("Dynamic kickoff line-up: coverage on the receiving 40, return setup zone 35-30, two returners deep, 5-yd run-up (disc images only; unwitnessed)")
        self.position_row_check = QCheckBox("Position on the first page of Edit Player, in roster mode and Franchise (Depth Chart -> Auto afterwards)")
        self.probowl_order_check = QCheckBox("Pro Bowl Votes tabs in football order: offence, defence, then K and P")
        self.penalties_check = QCheckBox("Penalties at NFL rates (estimated first cut: holding, DPI, roughing, face mask, clipping re-tuned; 15-yd face mask) + a working Chop Block toggle")
        self.uniform_choice_check = QCheckBox("Home/away jerseys at any stadium: up/down past the last era on Controller Assign or Team Select flips that side's colour (retail default kept; unwitnessed)")
        self.kick_laces_check = QCheckBox("Laces to the posts on field goals and PATs: the held ball rolls 180 degrees about its long axis on Field Goal formation plays (kickoff tee, punts and carries unchanged; unwitnessed)")
        self.franchise_practice_check = QCheckBox("Free Practice inside Franchise: a Practice row on the Coach's Desk runs a full scrimmage with your franchise roster, your away kit vs your home kit, and returns to the desk (no stats or injuries; unwitnessed)")
        self.seven_on_seven_check = QCheckBox("7-on-7 practice mode: Practice Type 7-On-7 + 7-on-7 sets in the practice playbook (linemen idle at the sideline, 4-second timer rusher; disc images only; unwitnessed)")
        self.player_star_check = QCheckBox("Star decal under the players you tag: the retail controller star follows every player ticked ★ Star in Text & Rosters, up to 9 at once (nothing changes with no tags; unwitnessed)")
        for box in (self.catch_check, self.accel_check, self.draft_check, self.returner_check, self.progression_check, self.team_column_check, self.team_history_check, self.prospect_names_check, self.kick_rules_check, self.kick_power_check, self.kickoff_alignment_check, self.overtime_check, self.season_check, self.position_row_check, self.probowl_order_check, self.penalties_check, self.uniform_choice_check, self.kick_laces_check, self.franchise_practice_check, self.player_star_check, self.seven_on_seven_check, self.roster_edits_check):
            g.addWidget(box)
        if not mod_build.SEVEN_ON_SEVEN_RELEASED:
            self.seven_on_seven_check.hide()
        self.star_players_label = QLabel("★ Star players: none ticked (tick them in Text & Rosters -> Current Roster Players).")
        self.star_players_label.setObjectName("throwMuted")
        self.star_players_label.setWordWrap(True)
        g.addWidget(self.star_players_label)
        g.addLayout(history_row)
        g.addLayout(names_row)
        g.addLayout(edits_row)
        root.addWidget(gameplay)

        text = QGroupBox("Text")
        tl = QVBoxLayout(text)
        self.edge_check = QCheckBox("Rename Defensive End to EDGE game-wide")
        self.scheme_labels_check = QCheckBox("Depth-chart positions by scheme: 4-3 SAM/MIKE/WILL, 3-4 EDGE/MIKE/WILL/NT")
        tl.addWidget(self.edge_check)
        tl.addWidget(self.scheme_labels_check)
        self.position_pools_check = QCheckBox("One EDGE / one LB / one interior pool across 4-3 and 3-4 (rosters, playbooks, free agency, draft; disc images only)")
        tl.addWidget(self.position_pools_check)
        root.addWidget(text)

        pres = QGroupBox("Presentation (disc images only)")
        pl = QVBoxLayout(pres)
        self.scorebug_check = QCheckBox("Modern ESPN scorebug bar (bottom centre, never swaps sides, stays up during plays) + repainted textures, kick meter lifted, lineup strip off")
        pl.addWidget(self.scorebug_check)
        self.camera_check = QCheckBox("Default camera: the Standard preset becomes the Far look (retail Far geometry and lens)")
        pl.addWidget(self.camera_check)
        self.widescreen_check = QCheckBox("Widescreen hor+ 16:9 (wider 3D view, HUD and menus keep 4:3 sizing; set xemu Display aspect to 16x9)")
        self.widescreen_check.setToolTip("v2 (9/3 night): one hook on camera activation - 3D full-screen views go hor+ (32/27), every 2D layer and every sub-window is pillarboxed and clipped to 4:3; "
                                         "xemu must display 16x9 (Settings -> Display -> aspect ratio, or [display.ui] aspect_ratio in xemu.toml).")
        pl.addWidget(self.widescreen_check)
        self.commentary_label = QLabel("Commentary swaps: none queued (use the Commentary tab to pick lines).")
        self.commentary_label.setObjectName("throwMuted")
        pl.addWidget(self.commentary_label)
        root.addWidget(pres)

        out = QHBoxLayout()
        out.addWidget(QLabel("Write copy to"))
        self.target_field = QLineEdit()
        out.addWidget(self.target_field, 1)
        self.target_button = QPushButton("Choose…")
        self.target_button.clicked.connect(self._choose_target)
        out.addWidget(self.target_button)
        root.addLayout(out)

        actions = QHBoxLayout()
        self.build_button = QPushButton("Build patched copy")
        self.build_button.clicked.connect(self._build)
        actions.addWidget(self.build_button)
        actions.addStretch(1)
        root.addLayout(actions)
        prog = QHBoxLayout()
        self.progress_label = QLabel("")
        self.progress_label.setObjectName("throwMuted")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.hide()
        prog.addWidget(self.progress_label, 1)
        prog.addWidget(self.progress_bar)
        root.addLayout(prog)
        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)
        root.addStretch(1)

        for box in (self.throw_check, self.catch_check, self.accel_check, self.draft_check,
                    self.returner_check, self.progression_check, self.edge_check, self.scorebug_check):
            box.toggled.connect(lambda _c: self._refresh())
        self.commentary: list[mod_build.CommentarySwap] = []
        self.star_players: list[str] = []

    # ------------------------------------------------------------- state
    def apply_state(self, state: dict[str, object]) -> None:
        """Populate from mod_build.inspect output (also used by tests)."""

        self._state = state
        self.source_field.setText(str(state.get("path", "")))
        is_image = state.get("container") == "xiso"
        bits = []
        settings = state.get("throw")
        if isinstance(settings, tt.TuningSettings):
            bits.append(f"throw ceiling {settings.max_deep_yards:g} yd" + (", realistic flight" if settings.realistic_flight else "") + (", arc by distance" if getattr(settings, 'arc_by_distance', False) else ""))
        for key, label in (("catch_slider", "catch/INT sliders"), ("accel_ramp", "acceleration ramp"),
                           ("draft_ai", "draft AI"), ("returner_fix", "returner fix"), ("progression", "progression"), ("team_column", "TEAM column"), ("team_history", "team history"), ("prospect_names", "prospect names"),
                           ("kick_rules", "kick rules"), ("kick_power", "kick power"), ("kickoff_alignment", "kickoff line-up"), ("overtime", "overtime"), ("season_2026", "2026 season"), ("position_row", "Position row"), ("probowl_order", "Pro Bowl order"), ("penalties", "penalties"), ("uniform_choice", "jersey choice"), ("kick_laces", "kick laces"), ("franchise_practice", "Franchise practice"), ("seven_on_seven", "7-on-7 practice"),
                           ("player_star", "star decal"), ("player_tags", "star tags"), ("roster_edits", "roster edits"),
                           ("edge_rename", "EDGE rename"), ("scheme_labels", "scheme labels"), ("position_pools", "one-pool positions"),
                           ("camera", "camera"), ("widescreen", "widescreen"),
                           ("scorebug", "ESPN scorebug")):
            bits.append(f"{label}: {state.get(key)}")
        # The disc's identity comes first: a repacked or pre-modded image decides whether Build
        # can work at all, and the user should read that before pressing the button, not after a
        # step refuses 40 minutes in.
        head = ("Disc image" if is_image else "default.xbe") + " read."
        identity = str(state.get("disc_identity_line") or "")
        if identity:
            head += " " + identity
        self.source_status.setText(head + " " + "; ".join(bits) + ".")
        # a patch already applied cannot be re-applied; a foreign site disables the toggle
        def gate(box: QCheckBox, key: str, needs_image: bool = False, module: str | None = None) -> None:
            value = str(state.get(key))
            available = self._available.get(module or key, True)
            box.setEnabled(available and value == "retail" and (is_image or not needs_image))
            box.setChecked(False)
            if not available:
                box.setToolTip("Not available in this build.")
            elif value == "applied":
                box.setToolTip("Already applied in this source.")
            elif value == "foreign":
                box.setToolTip("Bytes at the patch sites are neither retail nor this patch; refusing.")
            elif needs_image and not is_image:
                box.setToolTip("Needs a disc image.")
            else:
                box.setToolTip("")
        gate(self.catch_check, "catch_slider")
        gate(self.accel_check, "accel_ramp")
        gate(self.draft_check, "draft_ai")
        gate(self.returner_check, "returner_fix")
        gate(self.progression_check, "progression")
        gate(self.team_column_check, "team_column")
        gate(self.team_history_check, "team_history", needs_image=True)
        gate(self.prospect_names_check, "prospect_names", needs_image=True)
        # an already-edited roster can take more edits: gate on availability and the container only
        self.roster_edits_check.setEnabled(self._available.get("roster_edits", True) and is_image)
        self.roster_edits_check.setChecked(False)
        self.roster_edits_check.setToolTip("" if is_image else "Needs a disc image.")
        gate(self.kick_rules_check, "kick_rules")
        gate(self.kick_power_check, "kick_power", module="kick_rules")
        self.kick_rules_check.toggled.connect(lambda on: on and self.kick_power_check.setChecked(False))
        self.kick_power_check.toggled.connect(lambda on: on and self.kick_rules_check.setChecked(False))
        gate(self.kickoff_alignment_check, "kickoff_alignment", needs_image=True)
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
        gate(self.scorebug_check, "scorebug", needs_image=True)
        gate(self.camera_check, "camera")
        gate(self.widescreen_check, "widescreen")
        self.throw_check.setEnabled(True)
        self._refresh()

    def apply_preset(self, name: str) -> dict[str, list[str]]:
        """Tick the preset's toggles (only those the source can still take); returns what was skipped."""

        values = mod_build.PRESETS[name]
        boxes = {
            "throw": self.throw_check, "catch_slider": self.catch_check, "accel_ramp": self.accel_check,
            "draft_ai": self.draft_check, "returner_fix": self.returner_check, "progression": self.progression_check,
            "edge_rename": self.edge_check, "scorebug": self.scorebug_check, "scheme_labels": self.scheme_labels_check,
            "camera": self.camera_check, "kick_rules": self.kick_rules_check, "kick_power": self.kick_power_check,
            "position_pools": self.position_pools_check,
            "kickoff_alignment": self.kickoff_alignment_check,
            "season_2026": self.season_check, "widescreen": self.widescreen_check, "overtime": self.overtime_check,
            "team_column": self.team_column_check, "team_history": self.team_history_check,
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
        title = mod_build.PRESET_TITLES.get(name, name)
        if skipped:
            self.preset_note.setText(f"{title}: ticked {len(applied)}; not available on this source: "
                                     + ", ".join(skipped) + " (already applied, foreign bytes, or needs a disc image).")
        else:
            self.preset_note.setText(f"{title}: ticked {len(applied)} patches. Untick anything you do not want, then build.")
        return {"applied": applied, "skipped": skipped}

    def set_star_players(self, tags: list[str], names: list[str] | None = None) -> None:
        """The ★ Star ticks from Text & Rosters: the players the star decal follows."""

        self.star_players = [str(tag) for tag in tags]
        shown = list(names or self.star_players)
        if not self.star_players:
            self.star_players_label.setText(
                "★ Star players: none ticked (tick them in Text & Rosters -> Current Roster Players).")
        else:
            over = ("; the game draws at most 9 at once"
                    if len(self.star_players) > player_star.STAR_LIST_LIMIT else "")
            self.star_players_label.setText(
                f"★ Star players: {len(self.star_players)} ticked ({', '.join(shown[:8])}"
                + (", …" if len(shown) > 8 else "") + f"){over}. Needs a disc image.")
        self._refresh()

    def plan(self) -> mod_build.BuildPlan:
        return mod_build.BuildPlan(
            source=self.source_field.text(), target=self.target_field.text(),
            overwrite=Path(self.target_field.text()).exists() if self.target_field.text() else False,
            throw=self.throw_check.isChecked(), max_deep_yards=float(self.ceiling_spin.value()), arc=0.0,
            realistic_flight=self.realistic_check.isChecked(),
            arc_by_distance=self.arc_by_distance_check.isChecked(),
            catch_slider=self.catch_check.isChecked(), accel_ramp=self.accel_check.isChecked(),
            draft_ai=self.draft_check.isChecked(), edge_rename=self.edge_check.isChecked(),
            returner_fix=self.returner_check.isChecked(), progression=self.progression_check.isChecked(),
            scheme_labels=self.scheme_labels_check.isChecked(), camera=self.camera_check.isChecked(),
            kick_rules=self.kick_rules_check.isChecked(), kick_power=self.kick_power_check.isChecked(),
            position_pools=self.position_pools_check.isChecked(),
            kickoff_alignment=self.kickoff_alignment_check.isChecked(),
            season_2026=self.season_check.isChecked(), widescreen=self.widescreen_check.isChecked(),
            overtime=self.overtime_check.isChecked(), team_column=self.team_column_check.isChecked(), seven_on_seven=self.seven_on_seven_check.isChecked(),
            position_row=self.position_row_check.isChecked(), probowl_order=self.probowl_order_check.isChecked(),
            penalties=("nfl" if self.penalties_check.isChecked() else ""),
            uniform_choice=("choice" if self.uniform_choice_check.isChecked() else ""),
            kick_laces=self.kick_laces_check.isChecked(),
            franchise_practice=self.franchise_practice_check.isChecked(),
            player_star=self.player_star_check.isChecked(), player_tags=list(self.star_players),
            team_history=((self.team_history_field.text().strip() or "retail") if self.team_history_check.isChecked() else ""),
            prospect_names=((self.prospect_names_field.text().strip() or "modern") if self.prospect_names_check.isChecked() else ""),
            roster_edits=(self.roster_edits_field.text().strip() if self.roster_edits_check.isChecked() else ""),
            scorebug=self.scorebug_check.isChecked(), commentary=list(self.commentary),
        )

    def has_work(self) -> bool:
        p = self.plan()
        return bool(p.throw or p.catch_slider or p.accel_ramp or p.draft_ai or p.returner_fix or p.progression
                    or p.edge_rename or p.scorebug or p.scheme_labels or p.camera or p.kick_rules or p.kick_power or p.position_pools
                    or p.kickoff_alignment or p.season_2026 or p.widescreen or p.overtime or p.team_column or p.seven_on_seven or p.team_history or p.position_row or p.probowl_order or p.penalties or p.uniform_choice or p.kick_laces or p.franchise_practice or p.prospect_names or p.player_star or p.player_tags or p.roster_edits or p.commentary)

    def _refresh(self) -> None:
        self.ceiling_spin.setEnabled(self.throw_check.isChecked())
        self.realistic_check.setEnabled(self.throw_check.isChecked())
        self.arc_by_distance_check.setEnabled(self.throw_check.isChecked())
        self.build_button.setEnabled(bool(self.source_field.text()) and bool(self.target_field.text())
                                     and self.has_work() and self._task is None)

    # ------------------------------------------------------------ actions
    def _choose_source(self) -> None:
        chosen, _f = QFileDialog.getOpenFileName(self, "Choose default.xbe or a disc image", str(Path.home()), SOURCE_FILTER)
        if not chosen:
            return
        try:
            self.apply_state(mod_build.inspect(Path(chosen)))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Could not read the source", str(exc))

    def _choose_roster_edits(self) -> None:
        chosen, _f = QFileDialog.getOpenFileName(self, "Choose a roster-edits document", str(Path.home()),
                                                 "Roster edits (*.json);;All files (*)")
        if chosen:
            self.set_roster_edits(chosen)

    def set_roster_edits(self, path: str) -> None:
        """★ Rosters calls this when it writes a roster-edits document."""

        self.roster_edits_field.setText(path)
        self.roster_edits_check.setChecked(bool(path) and self.roster_edits_check.isEnabled())
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
        chosen, _f = QFileDialog.getSaveFileName(self, "Choose where to save the patched copy",
                                                 "ESPN NFL 2K5 (modded).xiso.iso" if is_image else "default_modded.xbe",
                                                 IMAGE_FILTER if is_image else XBE_FILTER)
        if chosen:
            self.target_field.setText(mod_build.image_target_path(chosen) if is_image else chosen)
            self._refresh()

    def _build(self) -> None:
        plan = self.plan()
        if not self.has_work():
            return
        answer = QMessageBox.question(
            self, "Build a patched copy?",
            f"Source (untouched): {plan.source}\n"
            + ("REPLACING existing copy: " if plan.overwrite else "New copy: ") + plan.target
            + "\n\nPatches: " + ", ".join(k for k, v in plan.to_recipe().items() if v is True)
            + "\n\nxemu-only: the RSA signature stays stale.",
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
        steps = ", ".join(str(s.get("step")) for s in receipt.get("steps", []))
        self.status_label.setText(f"Built {Path(str(receipt.get('target'))).name}: {steps}. Read-back state recorded in the receipt. "
                                  "Share tab: press Export to turn it into a .2k5patch for others.")
        self.built.emit(dict(receipt))
        QMessageBox.information(self, "Patched copy written", f"{receipt.get('target')}\n\nSteps: {steps}.")
        try:
            self.apply_state(mod_build.inspect(Path(str(receipt.get("target")))))
        except Exception:  # noqa: BLE001
            pass
        self._refresh()

    def _failed(self, message: str) -> None:
        self._task = None
        self.progress_bar.hide()
        self.progress_label.setText("")
        self.status_label.setText(f"Failed: {message}")
        QMessageBox.critical(self, "Build failed", message)
        self._refresh()


__all__ = ["BuildPanel"]
