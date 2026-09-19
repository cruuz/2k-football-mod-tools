"""Book selection, candidate editing and CPU previews in shell workers."""
from __future__ import annotations

from pathlib import Path
from mod_editor.gui.ux_text import plain_error

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout,
                             QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem,
                             QMessageBox, QPushButton, QScrollArea, QSlider, QSpinBox,
                             QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from . import playcalling_service as service
from mod_editor.core.errors import ValidationError
from .playbook_playcall_qt import ApfPlaycallPanel


def situation(down=1, distance_yards=10, yards_to_goal=50, period=2,
              clock_seconds=450, score_margin=0, timeouts=3):
    return dict(down=down, distance_yards=distance_yards, yards_to_goal=yards_to_goal,
                period=period, clock_seconds=clock_seconds, score_margin=score_margin,
                timeouts=timeouts, phase="scrimmage")


SITUATIONS = (
    ("1st and 10 midfield", situation()),
    ("2nd and short", situation(2, 2)), ("2nd and long", situation(2, 10)),
    ("3rd and 2", situation(3, 2)), ("3rd and 5", situation(3, 5)),
    ("3rd and 8", situation(3, 8)), ("3rd and 15", situation(3, 15)),
    ("Goal line", situation(1, 2, 2)), ("Red zone", situation(1, 10, 15)),
    ("Two-minute trailing", situation(1, 10, 60, 4, 110, -7, 2)),
    ("Two-minute leading", situation(1, 10, 60, 4, 110, 7, 2)),
    ("4th and 1", situation(4, 1)),
)


def note(layout, text):
    label = QLabel(text)
    label.setWordWrap(True)
    label.setTextFormat(Qt.PlainText)
    layout.addWidget(label)
    return label


def explain(widget, sentence):
    widget.setToolTip(sentence)
    widget.setAccessibleDescription(sentence)
    if not widget.accessibleName():
        widget.setAccessibleName(widget.text() if isinstance(widget, QPushButton) else sentence)
    return widget


def button(layout, text, sentence, slot):
    result = explain(QPushButton(text), sentence)
    result.clicked.connect(slot)
    layout.addWidget(result)
    return result


# Original model row stays attached to each item while Qt changes display order.
MODEL_ROW_ROLE = Qt.UserRole + 1


class SortableItem(QTableWidgetItem):
    def __lt__(self, other):
        def key(item):
            try:
                value = float(item.text())
                if value == value:  # NaN must not make ordering inconsistent.
                    return (0, value)
            except ValueError:
                pass
            return (1, item.text().casefold())
        left, right = key(self), key(other)
        if left == right:
            return self.data(MODEL_ROW_ROLE) < other.data(MODEL_ROW_ROLE)
        return left < right


def model_row(widget):
    item = widget.item(widget.currentRow(), 0)
    return int(item.data(MODEL_ROW_ROLE)) if item is not None else -1


def view_row(widget, original):
    return next((row for row in range(widget.rowCount())
                 if widget.item(row, 0).data(MODEL_ROW_ROLE) == original), -1)


def table(headers, name):
    result = QTableWidget(0, len(headers))
    result.setHorizontalHeaderLabels(headers)
    result.setAccessibleName(name)
    result.setSelectionBehavior(QAbstractItemView.SelectRows)
    result.setEditTriggers(QAbstractItemView.NoEditTriggers)
    result.setAlternatingRowColors(True)
    result.setWordWrap(True)
    result.horizontalHeader().setSortIndicator(-1, Qt.AscendingOrder)
    result.setSortingEnabled(True)
    return result


def fill(widget, rows):
    selected = model_row(widget)
    blocked = widget.blockSignals(True)
    sorting = widget.isSortingEnabled()
    widget.setSortingEnabled(False)
    try:
        widget.setRowCount(len(rows))
        for i, values in enumerate(rows):
            for j, value in enumerate(values):
                item = SortableItem(str(value))
                item.setData(MODEL_ROW_ROLE, i)
                item.setToolTip(str(value))
                widget.setItem(i, j, item)
    finally:
        widget.setSortingEnabled(sorting)
        if selected >= 0:
            widget.setCurrentCell(view_row(widget, selected), 0)
        widget.blockSignals(blocked)
    widget.resizeColumnsToContents()
    widget.resizeRowsToContents()


class ApfPlayCallingEditor(QWidget):
    modifiedChanged = pyqtSignal()
    manualBookAllocationRequested = pyqtSignal()

    def __init__(self, facade, run_task):
        super().__init__()
        self.facade, self.run_task = facade, run_task
        self._context = None
        self._book_source = None
        self._review = None
        self._pending = []
        self._pending_session = None
        self._pending_blockers = {}
        self._generation = 0
        self._busy = False
        self._loading = False
        self._updating = False
        self._custom_timer = QTimer(self)
        self._custom_timer.setSingleShot(True)
        self._custom_timer.setInterval(180)
        self._custom_timer.timeout.connect(self.refresh)
        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        root = QVBoxLayout(body)
        scroll.setWidget(body)
        outer.addWidget(scroll)
        note(root, "Pick a book, edit its formations and personnel, preview, then build. Stage edits, save your project, "
             "then Build a game copy. Percentages are an offline model; gameplay is UNWITNESSED.")
        self.candidate_search = explain(QLineEdit(), "Filter the selected situation's candidate formations and personnel. Clear the search to see every candidate again.")
        self.candidate_search.setAccessibleName("Search situation candidates")
        self.candidate_search.setPlaceholderText("Search formations or personnel… (Ctrl+F)")
        self.candidate_search.setProperty("studioSearch", True)
        self.candidate_search.setClearButtonEnabled(True)
        root.addWidget(self.candidate_search)

        self.team_controls = QGroupBox("Choose a book")
        team_root = QVBoxLayout(self.team_controls)
        picks = QHBoxLayout()
        self.team_picker = explain(QComboBox(), "Choose a team for an independent copy or a team tendency edit. Book previews keep the selected book.")
        self.team_picker.setAccessibleName("Team")
        self.side_picker = explain(QComboBox(), "Offense predicts calls for game situations; defense predicts responses to offensive personnel.")
        self.side_picker.addItem("Offense", "offense")
        self.side_picker.addItem("Defense", "defense")
        picks.addWidget(QLabel("Team")); picks.addWidget(self.team_picker)
        picks.addWidget(QLabel("Side")); picks.addWidget(self.side_picker)
        team_root.addLayout(picks)
        self.book_label = note(team_root, "Load a game folder to see each team's current book and the teams sharing it.")
        note(team_root, "An edit to a shared book changes calls for every team using it; give the team its own book to edit that team independently.")
        donors = QHBoxLayout()
        donors.addWidget(QLabel("Book to edit and preview"))
        self.donor_picker = explain(QComboBox(), "Edit and preview this book, including USER books. An independent copy also starts with this book's contents.")
        self.donor_picker.setAccessibleName("Book to edit and preview")
        donors.addWidget(self.donor_picker)
        team_root.addLayout(donors)
        note(team_root, "USER books supply their contents; global books are special-team supplements and may have no ordinary calls to preview.")
        row = QHBoxLayout()
        self.own_team_button = button(row, "Give this team its own book", "The game will use a separate copy of the selected starting book for this team after you review and stage the plan.", lambda: self.own_book(False))
        self.own_all_button = button(row, "Give every team its own book", "The game will use one independent copy of each team's current book on this side after you review and stage all 24 assignments.", lambda: self.own_book(True))
        team_root.addLayout(row)
        self.capacity_note = note(team_root, service.BOOK_CAPACITY_EXPLANATION)
        self.manual_books_button = button(team_root, "Manual book allocation…",
            "Open Book Identity's existing built-folder workflow for all 40 roster slots and unused labels. Build staged edits first.",
            lambda: self.manualBookAllocationRequested.emit())
        self.plan_table = table(("Team", "Label", "Donor", "Clone name"), "Own-book plan to review before staging")
        self.plan_table.setMaximumHeight(260)
        self.plan_table.setVisible(False)
        team_root.addWidget(self.plan_table)
        root.addWidget(self.team_controls)

        from mod_editor.core.apf2k8_offensive_schemes import SCHEMES
        self.scheme_group = QGroupBox("Scheme")
        scheme_root = QVBoxLayout(self.scheme_group)
        self.scheme_picker = explain(QComboBox(), "Choose an authored offensive scheme using this book's existing personnel and ratings.")
        self.scheme_picker.setAccessibleName("Offensive scheme")
        for scheme in SCHEMES:
            self.scheme_picker.addItem(scheme.name, scheme.id)
        scheme_root.addWidget(self.scheme_picker)
        self.scheme_note = note(scheme_root, "")
        def describe_scheme():
            scheme = SCHEMES[self.scheme_picker.currentIndex()]
            self.scheme_note.setText(scheme.description + " Preferred personnel: " + ", ".join(scheme.personnel_preference) +
                                     f". Team run tendency: {scheme.run_percentage}%. Reapplying adds the deltas again; Undo restores the prior edit.")
        self.scheme_picker.currentIndexChanged.connect(describe_scheme)
        describe_scheme()
        note(scheme_root, "ADVANCED, opt-in. Confirm checks the team copy and rating changes; then inspect the call preview. "
             "Row weights feed an optional cache; they do not override the CPU lottery. Per-situation run percentages "
             "are coaching intent. Tempo, snap count, weather ratio and coin toss have no proved control here.")
        self.scheme_button = button(scheme_root, "Confirm scheme for this team", "Check one team scheme, creating its own offensive book when shared; staging records one Undo step.", self.apply_scheme)
        self.scheme_export = button(scheme_root, "Export play call spreadsheet…", "Export the selected staged book in 23 situational buckets, with proxy rows, probabilities and limits.", self.export_scheme)
        self.scheme_details = table(("Setting", "Before", "After"), "Scheme changes to review")
        self.scheme_details.setVisible(False)
        self.scheme_details.setMaximumHeight(280)
        scheme_root.addWidget(self.scheme_details)
        root.addWidget(self.scheme_group)

        self.situation_group = QGroupBox("Situations and candidate formations")
        situation_root = QVBoxLayout(self.situation_group)
        self.situation_picker = explain(QComboBox(), "Inspect this situation's ordinary formation and personnel candidates, including low-weight candidates.")
        self.situation_picker.setAccessibleName("Situation to inspect and edit")
        situation_root.addWidget(self.situation_picker)
        self.situation_note = note(situation_root, "")
        note(situation_root, "Select a candidate to fine-tune its weights beside this table; personnel controls are below. Adding, removing or changing personnel edits the shared book, "
             "so it affects every situation using that data. These 23 preview buckets are not independent stored formation lists.")
        self.candidate_table = table(("Formation", "Personnel", "Requested\nTEs", "Personnel\nweight", "Formation\nweight"), "All ordinary situation candidates before the draw")
        self.candidate_table.setMaximumHeight(260)
        self.candidate_table.setMinimumHeight(180)
        candidate_row = QHBoxLayout()
        candidate_row.addWidget(self.candidate_table, 3)
        self.rating_editor = QGroupBox("Fine-tune formation weights")
        self.rating_editor.setToolTip(service.RATING_MAPPING)
        rating_root = QVBoxLayout(self.rating_editor)
        candidate_row.addWidget(self.rating_editor, 2)
        situation_root.addLayout(candidate_row)
        self.situation_remove = button(situation_root, "Confirm removal from this book", "Remove the selected ordinary formation completely from this book, including every situation; review remaining personnel first.", self.remove_candidate)
        donor_row = QHBoxLayout()
        self.add_donor = explain(QComboBox(), "Choose a book on the same side that already contains the formation to add.")
        self.add_donor.setAccessibleName("Formation donor book")
        self.add_formation = explain(QComboBox(), "Copy this ordinary formation's existing plays into the selected book. Its primary personnel comes from its proved package.")
        self.add_formation.setAccessibleName("Formation to add")
        donor_row.addWidget(QLabel("Add from book")); donor_row.addWidget(self.add_donor)
        donor_row.addWidget(self.add_formation)
        situation_root.addLayout(donor_row)
        self.add_button = button(situation_root, "Confirm formation addition", "Add the selected donor formation as an explicit book edit, then preview all affected situations.", self.stage_addition)
        self.bucket_export = button(situation_root, "Export play call spreadsheet…", "Export the selected offensive book in all 23 preview buckets, with their shared-data limits.", self.export_scheme)
        root.addWidget(self.situation_group)
        from .situation_mask_qt import SituationMaskPanel
        self.situation_masks = SituationMaskPanel(self)
        root.addWidget(self.situation_masks)
        # Existing scheme recipes remain loadable. The main workflow exposes
        # direct book edits; no scheme or preset is staged by visiting this page.
        self.scheme_group.hide()

        self.preview_group = QGroupBox("Live call preview")
        preview_root = QVBoxLayout(self.preview_group)
        note(preview_root, "The game draws a weighted call from these candidates; percentages describe possible calls, and recent plays or match state can change the result.")
        self.grid = table(("Situation / opposing personnel", "Requested row", "Top personnel", "Top formations", "Top plays", "What this means"), "Predicted CPU call distribution")
        self.grid.setMinimumHeight(300)
        preview_root.addWidget(self.grid)
        custom = QFormLayout()
        self.custom = {}
        for key, label, low, high, value, text in (
            ("down", "Down", 1, 4, 3, "The game uses the down to choose a situation row and adjust the run share."),
            ("distance_yards", "Yards to first down", 0, 99, 8, "The game uses yards to gain to weigh short, medium and long situations."),
            ("yards_to_goal", "Yards to goal", 0, 100, 50, "The game changes its personnel request near either goal line."),
            ("period", "Quarter", 1, 5, 4, "The game uses the quarter with the clock and score to assess urgency."),
            ("clock_seconds", "Seconds left in quarter", 0, 900, 110, "The game changes its run/pass choice as time runs out."),
            ("score_margin", "Team's points ahead (negative means behind)", -99, 99, -7, "The game treats a trailing team differently from a leading team late in the game."),
            ("timeouts", "Timeouts left", 0, 3, 2, "The game uses remaining timeouts when deciding whether there is time to run."),
        ):
            control = QDoubleSpinBox() if key in {"distance_yards", "yards_to_goal", "clock_seconds"} else QSpinBox()
            control.setRange(low, high); control.setValue(value)
            control.setAccessibleName(label)
            explain(control, text)
            custom.addRow(label, control)
            control.valueChanged.connect(self._custom_changed)
            self.custom[key] = control
        preview_root.addLayout(custom)
        self.preview_tendency = explain(QSpinBox(), "Preview run share is independent of the selected team; this changes the preview only.")
        self.preview_tendency.setRange(0, 100)
        self.preview_tendency.setValue(50)
        self.preview_tendency.setAccessibleName("Preview run share percent")
        custom.addRow("Preview run share (%)", self.preview_tendency)
        self.preview_tendency.valueChanged.connect(self._custom_changed)
        note(preview_root, "Change the custom situation to see what the game would weigh there; this changes the preview, not your book.")
        self.refresh_button = button(preview_root, "Refresh call preview", "Recalculate the selected book's modeled calls with the preview run share and situation.", self.refresh)
        root.addWidget(self.preview_group)

        self.levers = QGroupBox("Change how this book calls plays")
        lever_root = QVBoxLayout(self.levers)
        self.formation_picker = explain(QComboBox(), "The game uses this formation's ratings and personnel when it enters the call lottery.")
        self.formation_picker.setAccessibleName("Formation")
        rating_root.addWidget(QLabel("Formation")); rating_root.addWidget(self.formation_picker)
        note(rating_root, service.RATING_EXPLANATION)
        self.ratings = []
        rating_form = QFormLayout()
        for label in ("Short yardage", "Medium yardage", "Long yardage"):
            slider = QSlider(Qt.Horizontal); slider.setRange(0, 7)
            slider.setAccessibleName(label + " formation rating")
            explain(slider, f"The {label.lower()} raw rating contributes to both lotteries. "
                            "Zero favors the category more than one, but weighs less in the later formation draw. "
                            "Use the call preview to compare; neither value disables a formation.")
            value = QLabel("0")
            slider.valueChanged.connect(lambda v, target=value: target.setText(str(v)))
            row = QHBoxLayout(); row.addWidget(slider); row.addWidget(value)
            rating_form.addRow(label + " (raw 0–7)", row)
            self.ratings.append(slider)
        rating_root.addLayout(rating_form)
        self.ratings_button = button(rating_root, "Confirm formation ratings", "The game will use these three ratings for this formation in the built book.", self.stage_ratings)
        self.rating_preview_button = button(rating_root, "Preview formation weights",
            "Compare personnel and formation weights in every situation before confirming. Includes pending edits; nothing is staged.",
            self.preview_ratings)
        self.rating_preview_note = note(situation_root,
            "Select a formation here, change its short / medium / long raw ratings, then preview or Confirm. "
            "These shared ratings affect every situation that interpolates them; personnel and formation weights "
            "are calculated together, not independent percentages.")
        self.rating_preview_table = table(("Situation / personnel", "Personnel before", "Personnel after",
            "Formation before", "Formation after"), "Draft formation weights across situations")
        self.rating_preview_table.setMinimumHeight(180)
        self.rating_preview_table.setMaximumHeight(280)
        self.rating_preview_table.hide()
        situation_root.insertWidget(4, self.rating_preview_note)
        situation_root.insertWidget(5, self.rating_preview_table)
        for slider in self.ratings:
            slider.valueChanged.connect(self._clear_rating_preview)
        self.play_picker = explain(QComboBox(), "The game draws among the plays present in this formation.")
        self.play_picker.setAccessibleName("Play")
        lever_root.addWidget(self.play_picker)
        self.play_rating = QSpinBox(); self.play_rating.setRange(0, 7)
        self.play_rating.setAccessibleName("Play X rating")
        explain(self.play_rating, "Lower X increases initial play weight. Actual calls also depend on the situation, personnel, available plays and history.")
        lever_root.addWidget(self.play_rating)
        note(lever_root, "Play X rating: 0 = called most; larger numbers give the play less weight, alongside suitability and run/pass choice.")
        self.play_rating_button = button(lever_root, "Confirm play rating", "The game will use this X rating when choosing this play in the selected formation.", self.stage_play_rating)
        self.primary = explain(QComboBox(), "The game advertises this formation under its primary personnel category.")
        self.primary.setAccessibleName("Primary personnel")
        lever_root.addWidget(QLabel("Primary personnel")); lever_root.addWidget(self.primary)
        self.secondary = explain(QListWidget(), "The game may also reach this formation through each checked secondary personnel category.")
        self.secondary.setAccessibleName("Secondary personnel")
        self.secondary.setMaximumHeight(150)
        lever_root.addWidget(QLabel("Also available to these personnel categories")); lever_root.addWidget(self.secondary)
        note(lever_root, "Primary personnel is the formation's main category; checked secondary categories also make it available to the game's personnel selection.")
        self.categories_button = button(lever_root, "Confirm personnel change", "The game will advertise this formation under the chosen categories after you review the row coverage.", self.stage_categories)
        self.remove_button = button(lever_root, "Confirm remove formation", "The game will lose this formation and its plays from this book after you review the surviving personnel and confirm.", self.remove_formation)
        self.never_call = explain(QCheckBox("Never call (ordinary CPU lottery)"), "Exclude this ordinary formation without deleting its plays or moving records; explicit user calls and special calls are outside this control.")
        lever_root.addWidget(self.never_call)
        self.never_button = button(lever_root, "Confirm Never call", "Review this formation's CPU exclusion or restore its saved personnel memberships; Undo also restores it.", self.stage_never_call)
        note(lever_root, "Never call preserves the record and requires another formation for its personnel. "
             "Special formations 151–162 remain protected: their cached-call path bypasses this switch. "
             "A saved USER book or global merge can supply another copy. Reload the built book; gameplay is UNWITNESSED.")
        self.retire_picker = explain(QComboBox(), "The game will stop advertising this personnel category anywhere in this book if a valid replacement remains.")
        self.retire_picker.setAccessibleName("Personnel to retire")
        lever_root.addWidget(self.retire_picker)
        self.retire_button = button(lever_root, "Confirm retire personnel and run/pass share", "The game will lose this category from all surviving primary and secondary memberships after you review coverage and confirm.", self.retire)
        self.tendency = QSlider(Qt.Horizontal); self.tendency.setRange(0, 100)
        self.tendency.setAccessibleName("Team run share percent")
        explain(self.tendency, "The game starts from this team's run share, then adjusts it for down, distance, score and urgency.")
        self.tendency_label = note(lever_root, "Run share: 50%; pass share: 50%.")
        self.tendency.valueChanged.connect(lambda v: self.tendency_label.setText(f"Run share: {v}%; pass share: {100-v}%. The game adjusts this for the situation."))
        lever_root.addWidget(self.tendency)
        self.tendency_button = button(lever_root, "Confirm team run/pass tendency", "The game will use this run share for the selected team even when other teams share its book.", self.stage_tendency)
        self.audibles_button = button(lever_root, "Confirm balanced CPU audibles", "The game will use existing run and pass plays in each formation's audible slots; formations missing either kind cannot be balanced.", self.stage_audibles)
        note(lever_root, "Use Fine-tune Plays for individual audible slots; automatic balancing keeps each formation's existing plays.")
        root.addWidget(self.levers)

        self.review_group = QGroupBox("Pending edits")
        review_root = QVBoxLayout(self.review_group)
        self.queue_edits = explain(QCheckBox("Add edits to Pending edits"),
                                   "Collect any number of book, personnel, situation and team edits, then check and stage them with Confirm all.")
        review_root.addWidget(self.queue_edits)
        self.pending_table = table(("Edit", "Book / team / row", "Checks and next step", "Undo / clear"), "Pending edits")
        self.pending_table.setMaximumHeight(240)
        review_root.addWidget(self.pending_table)
        self.confirm_button = button(review_root, "Confirm all", "Run every review and the combined checks, then stage the clean set in one Undo step. Blocked edits stay in this list.", self.confirm_review)
        self.clear_pending_button = button(review_root, "Clear pending edits", "Discard the pending list without changing staged edits.", self.clear_pending)
        self.details_toggle = explain(QCheckBox("Show review details"), "Expand the coverage and retired personnel review. Reading it is optional; Confirm always runs these checks.")
        review_root.addWidget(self.details_toggle)
        self.review_details = QWidget()
        detail_root = QVBoxLayout(self.review_details)
        self.review_label = note(detail_root, "Confirm runs the writer, personnel and coverage checks automatically.")
        self.coverage_table = table(("Requested row", "Remaining personnel categories", "Coverage"), "Lineup resolver row coverage")
        self.coverage_table.setMaximumHeight(220)
        detail_root.addWidget(self.coverage_table)
        detail_root.addWidget(self.scheme_details)
        self.details_toggle.toggled.connect(self.review_details.setVisible)
        self.review_details.setVisible(False)
        review_root.addWidget(self.review_details)
        root.addWidget(self.review_group)

        self.master_group = QGroupBox("MASTER personnel: EXPERIMENTAL, changes every book on the disc")
        self.master_group.setCheckable(True); self.master_group.setChecked(False)
        explain(self.master_group, "Opening these experimental controls lets you change the personnel roles and rows used by every book on the disc.")
        master_layout = QVBoxLayout(self.master_group)
        self.master_body = QWidget()
        master_layout.addWidget(self.master_body)
        master_root = QVBoxLayout(self.master_body)
        self.master_group.toggled.connect(self.master_body.setVisible)
        self.master_body.setVisible(False)
        note(master_root, "Changes every book on the disc: the game uses these eleven roles to fill the lineup and the row to weigh personnel candidates.")
        self.master_table = table(("Category", "Name", "Row") + tuple(f"Player {i+1}" for i in range(11)), "All 28 MASTER personnel categories and eleven roles")
        self.master_table.setMinimumHeight(200)
        master_root.addWidget(self.master_table)
        self.master_row = QSpinBox(); self.master_row.setRange(0, 27)
        self.master_row.setAccessibleName("Personnel category row")
        explain(self.master_row, "The game compares this row with the requested personnel row when weighing this category in every book.")
        master_root.addWidget(self.master_row)
        self.master_row_button = button(master_root, "Confirm personnel row", "The game will compare this category at its new row in every book on the disc.", self.stage_master_row)
        self.roles = []
        role_form = QFormLayout()
        for i in range(11):
            control = explain(QComboBox(), f"The game fills player slot {i+1} with this role whenever it uses the selected category in any book.")
            control.setAccessibleName(f"Personnel role for player {i+1}")
            role_form.addRow(f"Player {i+1}", control)
            self.roles.append(control)
        master_root.addLayout(role_form)
        self.roles_button = button(master_root, "Confirm eleven personnel roles", "The game will fill this category's eleven lineup slots using these roles in every book on the disc.", self.stage_roles)
        note(master_root, "5-2 sits one row below the ordinary request, so the game never weighs it; move it to row 13 to make it an ordinary candidate. This refers to ordinary matchups; near-goal requests can differ.")
        self.fix_52_button = button(master_root, "Make 5-2 an ordinary candidate (row 13)", "The game will be able to weigh 5-2 against an ordinary defensive personnel request in every book carrying it.", self.fix_52)
        root.addWidget(self.master_group)

        self.receipt_table = table(("Control", "Book / team", "Before", "After", "Retired categories"), "Staged CPU Play Calling receipt")
        self.receipt_table.setMaximumHeight(240)
        root.addWidget(self.receipt_table)
        self.undo_button = button(root, "Undo last session change", "The next build uses the previous staged session state, including its prior book ownership plan.", self.undo)

        self.experiments = QGroupBox("Experimental patches")
        experiment_root = QVBoxLayout(self.experiments)
        note(experiment_root, "These patches change every CPU book while installed in Xenia. Both presets start off; installation requires consent and gameplay is UNWITNESSED.")
        note(experiment_root, "Installing a personnel curve preset replaces the previously installed personnel curve preset; the pass-fetch experiment has its own file.")
        note(experiment_root, "Retail weighs personnel one row from the request at "
             f"{service.RETAIL_CURVES['offense'][1]:g} on offense and {service.RETAIL_CURVES['defense'][1]:g} on defense; "
             f"the presets use {service.CURVE_PRESETS['offense'][1]:g} and {service.CURVE_PRESETS['defense'][1]:g}, so the game stays "
             "closer to the requested personnel. These preset numbers are authored, not measured in the game.")
        self.curve_profile = explain(QComboBox(), "Xenia applies the curve patch only to this executable profile; choose retail BASE or Title Update 1.1 to match your game.")
        self.curve_profile.addItem("Retail BASE", "base"); self.curve_profile.addItem("Title Update 1.1", "tu1")
        experiment_root.addWidget(self.curve_profile)
        self.curve_side = explain(QComboBox(), "The chosen preset reduces the weight of personnel farther from the requested situation for offense or defense.")
        self.curve_side.addItem("Offense: stick closer to the situation's personnel", "offense")
        self.curve_side.addItem("Defense: stick closer to the situation's personnel", "defense")
        experiment_root.addWidget(self.curve_side)
        self.curve_button = button(experiment_root, "Review and install personnel curve patch…", "Xenia will use a sharper personnel distance curve after you consent to installing the patch and enabling patches in its launch config.", self.install_curve)
        self.curve_status = note(experiment_root, "Personnel curve patch: not checked. Choose Check patch status to read the installed state.")
        self.curve_check = button(experiment_root, "Check personnel curve patch status", "The studio reads whether Xenia has this curve patch installed and enabled in the selected config.", self.check_curve)
        self.curve_remove = button(experiment_root, "Remove personnel curve patch", "Xenia returns to its unpatched personnel curve after removing this Studio patch and restarting.", self.remove_curve)
        # Keep the beta-66/P2 actions and consent flow as the maintained child.
        self.legacy = ApfPlaycallPanel(facade, run_task, patch_only=True)
        self.legacy.hide()
        experiment_root.addWidget(self.legacy.patch_controls)
        root.addWidget(self.experiments)
        self.notice = note(outer, "Load a game folder to start editing CPU Play Calling.")
        self.team_picker.currentIndexChanged.connect(self._selection_changed)
        self.side_picker.currentIndexChanged.connect(self._side_changed)
        self.donor_picker.currentIndexChanged.connect(self._selection_changed)
        self.formation_picker.currentIndexChanged.connect(self._formation_changed)
        self.play_picker.currentIndexChanged.connect(self._play_changed)
        self.master_table.itemSelectionChanged.connect(self._master_changed)
        self.situation_picker.currentIndexChanged.connect(self._situation_changed)
        self.candidate_table.itemSelectionChanged.connect(self._candidate_changed)
        self.candidate_search.textChanged.connect(self._filter_candidates)
        self.add_donor.currentIndexChanged.connect(self._add_donor_changed)
        root.insertWidget(1, self.queue_edits)
        self._confirm_labels = {control: control.text() for control in self.findChildren(QPushButton)
                                if control.text().startswith("Confirm ") and control is not self.confirm_button}
        self.queue_edits.toggled.connect(self._queue_mode_changed)
        self.set_context()

    def _source(self):
        return getattr(getattr(self.facade, "source", None), "index_0a", None)

    def _task(self, label, operation, done, blocking=False):
        generation, source = self._generation, self._source()
        self._loading = True
        self._enable()
        def work(progress):
            try:
                return operation(progress), None
            except ValidationError as exc:
                return None, str(exc)
            except Exception as exc:  # A contract call must never take the window down.
                return None, f"{label} could not finish: {plain_error(exc)}"
        def complete(result):
            if generation != self._generation or source != self._source():
                return
            self._loading = False
            value, error = result
            if error:
                self.notice.setText(error)
            else:
                try:
                    done(value)
                except Exception as exc:  # Show a broken result instead of crashing.
                    self.notice.setText(f"{label} returned something this page could not show: "
                                        + plain_error(exc))
            self._enable()
        accepted = self.run_task(label, work, complete, blocking)
        if accepted is False:
            self._loading = False
            self.notice.setText("Another operation is finishing. Try this action again when it finishes.")
            self._enable()

    def _enable(self):
        ready = bool(getattr(self.facade, "source_ready", False))
        enabled = ready and not self._busy and not self._loading
        self.team_controls.setEnabled(enabled)
        self.scheme_group.setEnabled(enabled and self._context is not None and self.side_picker.currentData() == "offense")
        self.preview_group.setEnabled(enabled)
        self.levers.setEnabled(enabled and self._context is not None)
        self.situation_group.setEnabled(enabled and self._context is not None)
        self.situation_masks.setEnabled(enabled and self._context is not None and self.side_picker.currentData() == "offense")
        self.bucket_export.setEnabled(enabled and self.side_picker.currentData() == "offense")
        self.master_group.setEnabled(enabled and self._context is not None)
        self.review_group.setEnabled(enabled)
        self.confirm_button.setEnabled(enabled and bool(self._pending))
        self.clear_pending_button.setEnabled(enabled and bool(self._pending))
        self.undo_button.setEnabled(enabled)
        self.experiments.setEnabled(not self._busy and not self._loading)

    def set_busy(self, busy):
        self._busy = bool(busy)
        self.legacy.set_busy(busy)
        self._enable()

    def set_context(self, *_):
        session = getattr(getattr(self.facade, "session", None), "session_id", None)
        if session != self._pending_session:
            self._pending = []
            self._pending_blockers = {}
            self._pending_session = session
            self._render_pending()
        self._generation += 1
        self._loading = False
        self._review = None
        self._context = None
        if self._book_source != self._source():
            self._updating = True
            self.donor_picker.clear()
            self._updating = False
            self._book_source = self._source()
        self._custom_timer.stop()
        self.scheme_details.setVisible(False)
        self.grid.setRowCount(0)
        self._situations = []
        self.candidate_table.setRowCount(0)
        self.plan_table.setRowCount(0)
        self.plan_table.setVisible(False)
        self.coverage_table.setRowCount(0)
        self._enable()
        if getattr(self.facade, "source_ready", False):
            self.refresh()

    def _selection_changed(self, *_):
        if not self._updating:
            self._review = None
            self.plan_table.setRowCount(0)
            self.plan_table.setVisible(False)
            self.refresh()

    def _side_changed(self, *_):
        if not self._updating:
            self._updating = True
            self.donor_picker.clear()
            self._updating = False
            self._selection_changed()

    def _custom_changed(self, *_):
        if not self._updating:
            self._custom_timer.start()

    def _rows(self, context, side):
        if side == "offense":
            custom = {key: control.value() for key, control in self.custom.items()}
            custom["phase"] = "scrimmage"
            return list(SITUATIONS) + [("Custom situation", custom)]
        by_row = {}
        for category in context["categories"]:
            if 0 <= category.row <= 10:
                by_row.setdefault(category.row, []).append(category.name)
        return [(f"Offense row {row}: " + ", ".join(by_row.get(row, ())),
                 {"offense_category_row": row, "yards_to_goal": self.custom["yards_to_goal"].value()}) for row in range(11)]

    def refresh(self):
        if not getattr(self.facade, "source_ready", False):
            return
        self._generation += 1
        self._review = None
        team, side = self.team_picker.currentData() or 0, self.side_picker.currentData()
        book = self.donor_picker.currentText() or None
        preview_tendency = self.preview_tendency.value()
        self.notice.setText("Recomputing calls from the selected staged book…")
        # Copy Qt values before entering a worker.
        custom = {key: control.value() for key, control in self.custom.items()}
        custom["phase"] = "scrimmage"
        try:
            snapshot = self.facade.playcalling_snapshot()
        except Exception as exc:  # No project state is worth losing the window over.
            self.notice.setText(f"CPU Play Calling could not read this project: {plain_error(exc)}")
            return
        def operation(progress):
            context = self.facade.playcalling_context(team, side, progress, book=book, preview_tendency=preview_tendency)
            if side == "offense":
                rows = list(SITUATIONS) + [("Custom situation", custom)]
            else:
                rows = [(f"Offense row {i}: " + ", ".join(c.name for c in context["categories"] if c.row == i),
                         {"offense_category_row": i, "yards_to_goal": custom["yards_to_goal"]}) for i in range(11)]
            return context, self.facade.playcalling_predict(context, side, rows, progress), self.facade.playcalling_situations(context, side)
        def done(result):
            if snapshot != self.facade.playcalling_snapshot():
                self.refresh()
                return
            self._context, predictions, self._situations = result
            self._render_context()
            self.render_grid(predictions)
            self.notice.setText("Preview recomputed from staged edits. Offline prediction; gameplay UNWITNESSED.")
        self._task("Predict CPU play calls", operation, done)

    def render_grid(self, predictions):
        def top(rows):
            return "\n".join(f"{name}: {probability:.1%}" for _, name, probability in rows[:3]) or "No candidates"
        fill(self.grid, [(label, call.requested_row, top(call.categories), top(call.formations), top(call.plays),
                          "\n".join(call.notes)) for label, call in predictions])

    def _render_context(self):
        c = self._context
        self.situation_masks.set_context(c, self.side_picker.currentData())
        self._updating = True
        previous_form = self.formation_picker.currentData()
        previous_situation = self.situation_picker.currentText()
        previous_add_donor = self.add_donor.currentText()
        self.team_picker.clear()
        for team in c["state"].teams:
            self.team_picker.addItem(team["team_name"], team["team_index"])
        self.team_picker.setCurrentIndex(self.team_picker.findData(c["team"]["team_index"]))
        users = c["users"]
        use = ("shared with " + ", ".join(users) if len(users) > 1 else
               "used only by " + users[0] if users else "not assigned to a disc team")
        self.book_label.setText(c["book"] + ", " + use + ". Selected team's assignment: " + c["team"][self.side_picker.currentData()] + ".")
        self.donor_picker.clear(); self.donor_picker.addItems(c["donors"])
        self.donor_picker.setCurrentIndex(max(0, self.donor_picker.findText(c["book"])))
        self.situation_picker.clear()
        self.situation_picker.addItems([row["name"] for row in self._situations])
        self.situation_picker.setCurrentIndex(max(0, self.situation_picker.findText(previous_situation)))
        self.add_donor.clear(); self.add_donor.addItems(c["donors"])
        self.add_donor.setCurrentIndex(max(0, self.add_donor.findText(previous_add_donor)))
        self.formation_picker.clear()
        for form in c["formations"]:
            self.formation_picker.addItem(form["name"], form["id"])
        self.formation_picker.setCurrentIndex(max(0, self.formation_picker.findData(previous_form)))
        self.primary.clear(); self.retire_picker.clear(); self.secondary.clear()
        for category in c["categories"]:
            label = f"{category.name} (row {category.row}; " + ", ".join(category.roles) + ")"
            self.primary.addItem(label, category.id); self.retire_picker.addItem(label, category.id)
            item = QListWidgetItem(label); item.setData(Qt.UserRole, category.id)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable); item.setCheckState(Qt.Unchecked)
            self.secondary.addItem(item)
        self.tendency.setValue(c["tendency"])
        fill(self.master_table, [(r.id, r.name, r.row, *r.roles) for r in c["categories"]])
        self._role_names = {}
        master = c["state"].master
        for category in c["categories"]:
            for i, name in enumerate(category.roles):
                self._role_names[master[0x49 + category.id * 16 + i] & 31] = name
        for control in self.roles:
            control.clear()
            for role, name in sorted(self._role_names.items()):
                control.addItem(name, role)
        if self.master_table.currentRow() < 0:
            self.master_table.selectRow(0)
        names = {r.id: r.name for r in c["categories"]}
        fill(self.receipt_table, [(e["request"]["kind"].replace("_", " "), e["request"].get("book", e["request"].get("team", "Every book / ownership")),
                                  e["before"], e["after"], ", ".join(names[i] for i in e["retired"])) for e in c["events"]])
        self._updating = False
        self._formation_changed()
        self._master_changed()
        self._situation_changed()
        self._add_donor_changed()

    def _situation_changed(self, *_):
        self._clear_rating_preview()
        if self._updating or not self._context or self.situation_picker.currentIndex() < 0:
            return
        row = self._situations[self.situation_picker.currentIndex()]
        self.situation_note.setText(f"Requested personnel row {row['row']}. " + row["note"] +
                                   " Weights are not percentages or exclusions. TE counts are requested roles; "
                                   "an empty TE depth list substitutes an FB.")
        names = {f["id"]: f["name"] for f in self._context["formations"]}
        self._updating = True
        fill(self.candidate_table, [(names.get(c["formation"], c["formation"]), c["personnel"], c["tight_ends"],
                                     f"{c['category_weight']:.4g}", f"{c['formation_weight']:.4g}") for c in row["candidates"]])
        self._updating = False
        header = self.candidate_table.horizontalHeader()
        header.setMinimumSectionSize(60)
        header.setSectionResizeMode(QHeaderView.Stretch)
        selected = next((i for i, c in enumerate(row["candidates"]) if c["formation"] == self.formation_picker.currentData()), None)
        self.situation_remove.setEnabled(selected is not None)
        if selected is not None:
            self.candidate_table.selectRow(view_row(self.candidate_table, selected))
        self._filter_candidates()

    def _filter_candidates(self):
        query = self.candidate_search.text().strip().casefold()
        for row in range(self.candidate_table.rowCount()):
            text = " ".join(self.candidate_table.item(row, column).text() for column in range(3)).casefold()
            hidden = bool(query and query not in text)
            self.candidate_table.setRowHidden(row, hidden)
            if hidden and self.candidate_table.currentRow() == row:
                self.candidate_table.setCurrentCell(-1, -1)
                self.situation_remove.setEnabled(False)

    def _candidate_changed(self):
        if self._updating or not self._context:
            return
        index = model_row(self.candidate_table)
        if index >= 0:
            candidate = self._situations[self.situation_picker.currentIndex()]["candidates"][index]
            self.formation_picker.setCurrentIndex(self.formation_picker.findData(candidate["formation"]))
            self.situation_remove.setEnabled(candidate["formation"] < 151)

    def remove_candidate(self):
        index = model_row(self.candidate_table)
        if self._context and index >= 0:
            candidate = self._situations[self.situation_picker.currentIndex()]["candidates"][index]
            self.review_request(self._book_request("remove", formation=candidate["formation"]), True)

    def _add_donor_changed(self, *_):
        if self._updating or not self._context:
            return
        from mod_editor.core import apf2k8_splb_writer as splb
        c = self._context
        body = c["state"].books.get(self.add_donor.currentText())
        self.add_formation.clear()
        if body is None:
            return
        names = {int(row["index"]): row["name"] for row in c["state"].inventory.get("formations", ())}
        present = {f["id"] for f in c["formations"]}
        for record in splb.parse_book(body, 0).records:
            form = record.formation_index
            if record.populated and form < 151 and form not in present:
                self.add_formation.addItem(names.get(form, str(form)), form)
                present.add(form)
        self.add_button.setEnabled(self.add_formation.count() > 0)

    def stage_addition(self):
        if self.add_formation.currentData() is not None:
            self.review_request(self._book_request("add", donor=self.add_donor.currentText(), formation=self.add_formation.currentData()), True)

    def _formation_changed(self, *_):
        self._clear_rating_preview()
        if self._updating or not self._context:
            return
        form = next((f for f in self._context["formations"] if f["id"] == self.formation_picker.currentData()), None)
        if form is None:
            return
        if self.situation_picker.currentIndex() >= 0:
            candidates = self._situations[self.situation_picker.currentIndex()]["candidates"]
            current = model_row(self.candidate_table)
            if not 0 <= current < len(candidates) or candidates[current]["formation"] != form["id"]:
                selected = next((i for i, c in enumerate(candidates) if c["formation"] == form["id"]), -1)
                self.candidate_table.blockSignals(True)
                self.candidate_table.setCurrentCell(view_row(self.candidate_table, selected), 0 if selected >= 0 else -1)
                self.candidate_table.blockSignals(False)
        self.never_call.setChecked(form.get("never_call", False))
        self.never_call.setEnabled(form["id"] < 151)
        self.never_button.setEnabled(form["id"] < 151)
        for slider, value in zip(self.ratings, form["ratings"]):
            slider.setValue(value)
        self.play_picker.clear()
        for play, name, rating in form["plays"]:
            self.play_picker.addItem(name, (play, rating))
        self.primary.setCurrentIndex(self.primary.findData(form["primary"]))
        for i in range(self.secondary.count()):
            item = self.secondary.item(i)
            item.setCheckState(Qt.Checked if item.data(Qt.UserRole) in form["secondary"] else Qt.Unchecked)
        self._play_changed()

    def _play_changed(self, *_):
        data = self.play_picker.currentData()
        if data:
            self.play_rating.setValue(data[1])

    def _master_changed(self):
        if self._updating or not self._context or self.master_table.currentRow() < 0:
            return
        category = self._context["categories"][model_row(self.master_table)]
        self.master_row.setValue(category.row)
        for i, control in enumerate(self.roles):
            role = self._context["state"].master[0x49 + category.id * 16 + i] & 31
            control.setCurrentIndex(control.findData(role))

    def _book_request(self, kind, **values):
        if not self._context:
            return None
        return {"kind": kind, "book": self._context["book"], **values}

    def _queue_mode_changed(self, queued):
        for control, label in self._confirm_labels.items():
            control.setText("Add " + label[len("Confirm "):] + " to pending" if queued else label)
        self.situation_masks.render()

    def _render_pending(self):
        self._clear_rating_preview()
        self.pending_table.clearContents()
        fill(self.pending_table, [(*service.PlayCallingService.describe_request(request),
                                  self._pending_blockers.get(i, "Checks run on Confirm all"), "")
                                 for i, request in enumerate(self._pending)])
        for i in range(len(self._pending)):
            clear = explain(QPushButton("Undo / clear"), "Remove only this pending edit; staged edits stay in the project.")
            clear.clicked.connect(lambda checked=False, row=i: self.clear_pending(row))
            self.pending_table.setCellWidget(view_row(self.pending_table, i), 3, clear)
        header = self.pending_table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(QHeaderView.Fixed)
        for column, width in ((0, 150), (1, 210), (3, 120)):
            self.pending_table.setColumnWidth(column, width)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        self.pending_table.setWordWrap(True)
        self.pending_table.setTextElideMode(Qt.ElideNone)
        self.pending_table.resizeRowsToContents()
        self._enable()
        if self._context:
            self.situation_masks.render()

    def clear_pending(self, row=None):
        if type(row) is int:
            del self._pending[row]
        else:
            self._pending.clear()
        self._pending_blockers.clear()
        self._render_pending()
        if self._context:
            self.situation_masks.set_context(self._context, self.side_picker.currentData())

    def review_request(self, request, confirm=False):
        # Historical callers all come here, including the live situation panel.
        # `confirm` is retained for compatibility; every action now checks itself.
        if request is not None:
            self.submit_requests([request])

    def submit_requests(self, requests):
        from copy import deepcopy
        requests = deepcopy(requests)
        if self.queue_edits.isChecked():
            self._pending.extend(requests)
            self._render_pending()
            self.notice.setText(f"{len(self._pending)} pending edits. Confirm all runs the checks together.")
            return
        self._confirm_requests(requests, queued=False)

    def _show_reviews(self, reviews, blockers=None):
        self.scheme_details.setVisible(False)
        rows, messages = [], []
        for review in reviews:
            self._review = review
            event, names = review['event'], review['category_names']
            what, where = service.PlayCallingService.describe_request(event['request'])
            outcome = event['warning'] or "Writer checks passed."
            if review.get('index') in (blockers or {}):
                outcome += " Combined queue checks blocked staging: " + blockers[review['index']]
            messages.append(f"{what}, {where}: " + outcome +
                            " Retired categories: " + (", ".join(review['retired_names']) or "none") + ".")
            if event['request']['kind'] == 'scheme' and event['after'] is not None:
                receipt = event['after']['scheme_receipt']
                settings = [("Team run %", receipt['run_percentage_before'], receipt['run_percentage_after'])]
                settings += [(f"Formation {r['formation']} ({r['personnel']})", r['before'], r['after']) for r in receipt['formations']]
                settings += [(f"Optional row {i} run/pass", [v[i] for v in receipt['row_weights_before']],
                              [v[i] for v in receipt['row_weights_after']]) for i in range(11)]
                fill(self.scheme_details, settings)
                self.scheme_details.setVisible(True)
                messages.append("Missing preferred personnel: " + (", ".join(receipt['missing_preferred_personnel']) or "none") + ". " + " ".join(receipt['notes']))
            rows.extend((f"{where}: {row}", ", ".join(names[i] for i in ids) or "None",
                         "Covered" if ids else "No candidate") for row, ids in event['coverage'].items())
        fill(self.coverage_table, rows)
        self.review_label.setText("\n".join(messages))

    def _confirmed(self, requests, result, *, queued):
        staged = set(result['staged'])
        blocked = {b['index']: f"{b['why']} Fix: {b['fix']}" for b in result['blockers']}
        remaining = [r for i, r in enumerate(requests) if i not in staged]
        offset = 0 if queued else len(self._pending)
        if queued:
            self._pending = remaining
            self._pending_blockers.clear()
        else:
            self._pending.extend(remaining)
        for row, i in enumerate(i for i in range(len(requests)) if i not in staged):
            self._pending_blockers[offset + row] = blocked[i]
        self._render_pending()
        if staged:
            for i in sorted(staged):
                request = requests[i]
                if request['kind'] in {'clones', 'scheme'}:
                    own = next((r['clone_name'] for r in request['assignments'] if r['team_index'] == self.team_picker.currentData()), None)
                    if own:
                        self._updating = True
                        self.donor_picker.addItem(own)
                        self.donor_picker.setCurrentText(own)
                        self._updating = False
            self.modifiedChanged.emit()
            self.refresh()
        self._show_reviews(result['reviews'], blocked)
        self.notice.setText(f"Staged {len(staged)} edits in one Undo step. " +
                            ("\n".join(blocked.values()) if blocked else "All checks passed."))

    def _confirm_requests(self, requests, *, queued):
        self._task("Confirm CPU Play Calling edits", lambda p: self.facade.confirm_playcalling(requests, p),
                   lambda result: self._confirmed(requests, result, queued=queued), True)

    def confirm_review(self):
        if self._pending:
            from copy import deepcopy
            self._confirm_requests(deepcopy(self._pending), queued=True)

    def _planned_edit(self, label, plan):
        queued = self.queue_edits.isChecked()
        def operation(progress):
            request = plan(progress)
            result = None if queued else self.facade.confirm_playcalling([request], progress)
            return request, result
        def done(value):
            request, result = value
            fill(self.plan_table, [(r["team_name"], r["label_id"], r["donor_name"], r["clone_name"]) for r in request["assignments"]])
            self.plan_table.setVisible(bool(request["assignments"]))
            if queued:
                self.submit_requests([request])
            else:
                self._confirmed([request], result, queued=False)
        self._task(label, operation, done, not queued)

    def own_book(self, every):
        if not self._context:
            return
        side = self.side_picker.currentData()
        team = None if every else self.team_picker.currentData()
        donor = None if every else self.donor_picker.currentText()
        self._planned_edit("Confirm independent team books", lambda p: self.facade.playcalling_plan(side, team, donor, p))

    def apply_scheme(self):
        if self._context:
            team, scheme_id = self.team_picker.currentData(), self.scheme_picker.currentData()
            self._planned_edit("Confirm team scheme", lambda p: self.facade.playcalling_scheme_plan(team, scheme_id, p))

    def export_scheme(self):
        team = self.team_picker.currentData()
        book = self.donor_picker.currentText()
        preview_tendency = self.preview_tendency.value()
        snapshot = self.facade.playcalling_snapshot()
        def ready(payload):
            if snapshot != self.facade.playcalling_snapshot():
                self.notice.setText("Project changed while making the spreadsheet; export again.")
                return
            path, _ = QFileDialog.getSaveFileName(self, "Export play call spreadsheet", "apf-play-calls.csv", "CSV spreadsheet (*.csv)")
            if path:
                from .launcher import _atomic_bytes
                try:
                    _atomic_bytes(Path(path), payload)
                except OSError as exc:
                    self.notice.setText(f"Could not save the spreadsheet: {exc}. Choose a writable folder and export again.")
                    return
                self.notice.setText("Exported current staged play calls to " + path + ". Gameplay is UNWITNESSED.")
        self._task("Make play call spreadsheet", lambda p: self.facade.playcalling_scheme_csv(team, p, book=book, preview_tendency=preview_tendency), ready)

    def _clear_rating_preview(self, *_):
        self.rating_preview_table.hide()
        self.rating_preview_note.setText(
            "Select a formation here, change its short / medium / long raw ratings, then preview or Confirm. "
            "These shared ratings affect every situation that interpolates them; personnel and formation weights "
            "are calculated together, not independent percentages.")

    def preview_ratings(self):
        if not self._context or self.formation_picker.currentData() is None:
            return
        from copy import deepcopy
        context, side = self._context, self.side_picker.currentData()
        formation = self.formation_picker.currentData()
        ratings = [s.value() for s in self.ratings]
        pending = deepcopy(self._pending)
        def done(result):
            rows = []
            selected = self.situation_picker.currentText()
            selected_row = 0
            for before, after in zip(result["before"], result["after"]):
                old = {c["category"]: c for c in before["candidates"] if c["formation"] == formation}
                for candidate in after["candidates"]:
                    if candidate["formation"] != formation:
                        continue
                    prior = old.get(candidate["category"], {})
                    if after["name"] == selected:
                        selected_row = len(rows)
                    rows.append((after["name"] + " / " + candidate["personnel"],
                        f"{prior.get('category_weight', 0):.4g}", f"{candidate['category_weight']:.4g}",
                        f"{prior.get('formation_weight', 0):.4g}", f"{candidate['formation_weight']:.4g}"))
            fill(self.rating_preview_table, rows)
            self.rating_preview_table.show()
            selected_row = view_row(self.rating_preview_table, selected_row)
            self.rating_preview_table.selectRow(selected_row)
            self.rating_preview_table.scrollToItem(self.rating_preview_table.item(selected_row, 0))
            self.rating_preview_note.setText(
                f"Draft preview for {context['book']}, {self.formation_picker.currentText()}, raw ratings {ratings}. "
                f"Includes {len(pending)} pending edits. All affected situations are shown; nothing staged. "
                "Confirm runs the checks again. Weights are neutral model inputs, not call percentages; gameplay UNWITNESSED.")
        self._task("Preview formation weights", lambda p: self.facade.preview_playcalling_ratings(
            context, side, formation, ratings, pending), done)

    def stage_ratings(self):
        self.review_request(self._book_request("ratings", formation=self.formation_picker.currentData(), ratings=[s.value() for s in self.ratings]))

    def stage_play_rating(self):
        if self.play_picker.currentData():
            self.review_request(self._book_request("play_rating", formation=self.formation_picker.currentData(), play=self.play_picker.currentData()[0], value=self.play_rating.value()))

    def stage_categories(self):
        secondary = [self.secondary.item(i).data(Qt.UserRole) for i in range(self.secondary.count()) if self.secondary.item(i).checkState() == Qt.Checked]
        self.review_request(self._book_request("categories", formation=self.formation_picker.currentData(), primary=self.primary.currentData(), secondary=secondary), True)

    def remove_formation(self):
        self.review_request(self._book_request("remove", formation=self.formation_picker.currentData()), True)

    def stage_never_call(self):
        form = next((f for f in self._context["formations"] if f["id"] == self.formation_picker.currentData()), None)
        if form is None:
            return
        if not form.get("restore_masks"):
            self.notice.setText("This book has no saved membership to restore; use Undo or reopen the original book.")
            return
        self.review_request(self._book_request("never_call", formation=form["id"], never=self.never_call.isChecked(), restore_masks=form["restore_masks"]), True)

    def retire(self):
        request = self._book_request("retire", category=self.retire_picker.currentData())
        if request is not None:
            self.submit_requests([request, {"kind": "tendency", "team": self.team_picker.currentData(), "value": self.tendency.value()}])

    def stage_tendency(self):
        self.review_request({"kind": "tendency", "team": self.team_picker.currentData(), "value": self.tendency.value()})

    def stage_audibles(self):
        self.review_request(self._book_request("audibles"))

    def _category_id(self):
        row = model_row(self.master_table)
        return self._context["categories"][row].id if row >= 0 and self._context else None

    def stage_master_row(self):
        if self._category_id() is not None:
            self.review_request({"kind": "master_row", "category": self._category_id(), "row": self.master_row.value()})

    def stage_roles(self):
        if self._category_id() is not None:
            self.review_request({"kind": "master_roles", "category": self._category_id(), "roles": [c.currentData() for c in self.roles]})

    def fix_52(self):
        if self._context:
            category = next((c.id for c in self._context["categories"] if c.name.replace(" ", "").split(":")[0] in {"5-2", "52"}), None)
            if category is not None:
                self.review_request({"kind": "master_row", "category": category, "row": 13})
            else:
                self.notice.setText("This MASTER has no named 5-2 category; inspect its personnel rows before editing.")

    def undo(self):
        def done(_):
            self._updating = True
            self.donor_picker.clear()
            self._updating = False
            self.modifiedChanged.emit()
            self.refresh()
        self._task("Undo session change", lambda p: self.facade.undo(p), done, True)

    def install_curve(self):
        side, profile = self.curve_side.currentData(), self.curve_profile.currentData()
        def done(prepared):
            answer = QMessageBox.question(self, "Install and enable the personnel curve experiment?",
                f"Install this patch at:\n{prepared['patch_path']}\n\nSet apply_patches = true in:\n{prepared['config_path']}\n\n"
                "This affects every book and also activates other patches marked enabled in Xenia's patches folder. "
                "The Studio launches with this config. Restart Xenia after changing patches. Gameplay is UNWITNESSED.",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if answer == QMessageBox.Yes:
                self._task("Install personnel curve patch", lambda p: self.facade.install_playcalling_curve(prepared, consent=True),
                           lambda status: self.curve_status.setText(status["message"]), True)
        self._task("Prepare personnel curve experiment", lambda p: self.facade.prepare_playcalling_curve(profile, side), done)

    def check_curve(self):
        self._task("Check personnel curve patch", lambda p: self.facade.playcalling_curve_status(), lambda status: self.curve_status.setText(status["message"]))

    def remove_curve(self):
        self._task("Remove personnel curve patch", lambda p: self.facade.remove_playcalling_curve(), lambda status: self.curve_status.setText(status["message"]), True)
