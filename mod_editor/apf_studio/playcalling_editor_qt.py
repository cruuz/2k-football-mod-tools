"""Team-first CPU Play Calling workspace; all model calls run in shell workers."""
from __future__ import annotations

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import (QAbstractItemView, QComboBox, QDoubleSpinBox, QFormLayout,
                             QGroupBox, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
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


def table(headers, name):
    result = QTableWidget(0, len(headers))
    result.setHorizontalHeaderLabels(headers)
    result.setAccessibleName(name)
    result.setSelectionBehavior(QAbstractItemView.SelectRows)
    result.setEditTriggers(QAbstractItemView.NoEditTriggers)
    result.setAlternatingRowColors(True)
    result.setWordWrap(True)
    return result


def fill(widget, rows):
    widget.setRowCount(len(rows))
    for i, values in enumerate(rows):
        for j, value in enumerate(values):
            item = QTableWidgetItem(str(value))
            item.setToolTip(str(value))
            widget.setItem(i, j, item)
    widget.resizeColumnsToContents()
    widget.resizeRowsToContents()


class ApfPlayCallingEditor(QWidget):
    modifiedChanged = pyqtSignal()

    def __init__(self, facade, run_task):
        super().__init__()
        self.facade, self.run_task = facade, run_task
        self._context = None
        self._review = None
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
        note(root, "CPU Play Calling predicts the calls this team's book can produce. Stage edits, save your project, "
             "then Build a game copy. Percentages are an offline model; gameplay is UNWITNESSED.")

        self.team_controls = QGroupBox("Choose a team and its book")
        team_root = QVBoxLayout(self.team_controls)
        picks = QHBoxLayout()
        self.team_picker = explain(QComboBox(), "The game uses the selected team's assigned book for its CPU calls.")
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
        donors.addWidget(QLabel("Starting book for a new copy"))
        self.donor_picker = explain(QComboBox(), "The game starts the new book with this donor's formations, plays and personnel; USER and global books use the same selector.")
        self.donor_picker.setAccessibleName("Starting book donor")
        donors.addWidget(self.donor_picker)
        team_root.addLayout(donors)
        note(team_root, "USER books supply their contents; global books are special-team supplements and may have no ordinary calls to preview.")
        row = QHBoxLayout()
        self.own_team_button = button(row, "Give this team its own book", "The game will use a separate copy of the selected starting book for this team after you review and stage the plan.", lambda: self.own_book(False))
        self.own_all_button = button(row, "Give every team its own book", "The game will use one independent copy of each team's current book on this side after you review and stage all 24 assignments.", lambda: self.own_book(True))
        team_root.addLayout(row)
        self.plan_table = table(("Team", "Label", "Donor", "Clone name"), "Own-book plan to review before staging")
        self.plan_table.setMaximumHeight(260)
        team_root.addWidget(self.plan_table)
        root.addWidget(self.team_controls)

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
        note(preview_root, "Change the custom situation to see what the game would weigh there; this changes the preview, not your book.")
        self.refresh_button = button(preview_root, "Refresh call preview", "The preview recalculates the game's modeled calls using the current staged book, personnel and team tendency.", self.refresh)
        root.addWidget(self.preview_group)

        self.levers = QGroupBox("Change how this book calls plays")
        lever_root = QVBoxLayout(self.levers)
        self.formation_picker = explain(QComboBox(), "The game uses this formation's ratings and personnel when it enters the call lottery.")
        self.formation_picker.setAccessibleName("Formation")
        lever_root.addWidget(QLabel("Formation")); lever_root.addWidget(self.formation_picker)
        note(lever_root, service.RATING_EXPLANATION)
        note(lever_root, service.RATING_MAPPING)
        self.ratings = []
        rating_form = QFormLayout()
        for label in ("Short yardage", "Medium yardage", "Long yardage"):
            slider = QSlider(Qt.Horizontal); slider.setRange(0, 7)
            slider.setAccessibleName(label + " formation rating")
            explain(slider, f"A higher {label.lower()} rating makes this formation more likely in that kind of situation.")
            value = QLabel("0")
            slider.valueChanged.connect(lambda v, target=value: target.setText(str(v)))
            row = QHBoxLayout(); row.addWidget(slider); row.addWidget(value)
            rating_form.addRow(label + " (0 to 7)", row)
            self.ratings.append(slider)
        lever_root.addLayout(rating_form)
        self.ratings_button = button(lever_root, "Stage formation ratings", "The game will use these three ratings for this formation in the built book.", self.stage_ratings)
        self.play_picker = explain(QComboBox(), "The game draws among the plays present in this formation.")
        self.play_picker.setAccessibleName("Play")
        lever_root.addWidget(self.play_picker)
        self.play_rating = QSpinBox(); self.play_rating.setRange(0, 7)
        self.play_rating.setAccessibleName("Play X rating")
        explain(self.play_rating, "The game weighs lower X ratings more heavily; 0 is called most, and 7 has the least weight.")
        lever_root.addWidget(self.play_rating)
        note(lever_root, "Play X rating: 0 = called most; larger numbers give the play less weight, alongside suitability and run/pass choice.")
        self.play_rating_button = button(lever_root, "Stage play rating", "The game will use this X rating when choosing this play in the selected formation.", self.stage_play_rating)
        self.primary = explain(QComboBox(), "The game advertises this formation under its primary personnel category.")
        self.primary.setAccessibleName("Primary personnel")
        lever_root.addWidget(QLabel("Primary personnel")); lever_root.addWidget(self.primary)
        self.secondary = explain(QListWidget(), "The game may also reach this formation through each checked secondary personnel category.")
        self.secondary.setAccessibleName("Secondary personnel")
        self.secondary.setMaximumHeight(150)
        lever_root.addWidget(QLabel("Also available to these personnel categories")); lever_root.addWidget(self.secondary)
        note(lever_root, "Primary personnel is the formation's main category; checked secondary categories also make it available to the game's personnel selection.")
        self.categories_button = button(lever_root, "Review personnel change", "The game will advertise this formation under the chosen categories after you review the row coverage.", self.stage_categories)
        self.remove_button = button(lever_root, "Remove formation", "The game will lose this formation and its plays from this book after you review the surviving personnel and confirm.", self.remove_formation)
        self.retire_picker = explain(QComboBox(), "The game will stop advertising this personnel category anywhere in this book if a valid replacement remains.")
        self.retire_picker.setAccessibleName("Personnel to retire")
        lever_root.addWidget(self.retire_picker)
        self.retire_button = button(lever_root, "Retire personnel", "The game will lose this category from all surviving primary and secondary memberships after you review coverage and confirm.", self.retire)
        self.tendency = QSlider(Qt.Horizontal); self.tendency.setRange(0, 100)
        self.tendency.setAccessibleName("Team run share percent")
        explain(self.tendency, "The game starts from this team's run share, then adjusts it for down, distance, score and urgency.")
        self.tendency_label = note(lever_root, "Run share: 50%; pass share: 50%.")
        self.tendency.valueChanged.connect(lambda v: self.tendency_label.setText(f"Run share: {v}%; pass share: {100-v}%. The game adjusts this for the situation."))
        lever_root.addWidget(self.tendency)
        self.tendency_button = button(lever_root, "Stage team run/pass tendency", "The game will use this run share for the selected team even when other teams share its book.", self.stage_tendency)
        self.audibles_button = button(lever_root, "Stage balanced CPU audibles", "The game will use existing run and pass plays in each formation's audible slots; formations missing either kind cannot be balanced.", self.stage_audibles)
        note(lever_root, "Use Fine-tune Plays for individual audible slots; automatic balancing keeps each formation's existing plays.")
        root.addWidget(self.levers)

        self.review_group = QGroupBox("Review before staging")
        review_root = QVBoxLayout(self.review_group)
        self.review_label = note(review_root, "A removal or personnel change lists retired categories and the lineup resolver's remaining candidates before you confirm.")
        self.coverage_table = table(("Requested row", "Remaining personnel categories", "Coverage"), "Lineup resolver row coverage")
        self.coverage_table.setMaximumHeight(220)
        review_root.addWidget(self.coverage_table)
        self.confirm_button = button(review_root, "Confirm and stage reviewed edit", "The game copy will include exactly the reviewed change; Undo restores the previous staged recipe.", self.confirm_review)
        self.confirm_button.setEnabled(False)
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
        self.master_row = QSpinBox(); self.master_row.setRange(0, 63)
        self.master_row.setAccessibleName("Personnel category row")
        explain(self.master_row, "The game compares this row with the requested personnel row when weighing this category in every book.")
        master_root.addWidget(self.master_row)
        self.master_row_button = button(master_root, "Stage personnel row", "The game will compare this category at its new row in every book on the disc.", self.stage_master_row)
        self.roles = []
        role_form = QFormLayout()
        for i in range(11):
            control = explain(QComboBox(), f"The game fills player slot {i+1} with this role whenever it uses the selected category in any book.")
            control.setAccessibleName(f"Personnel role for player {i+1}")
            role_form.addRow(f"Player {i+1}", control)
            self.roles.append(control)
        master_root.addLayout(role_form)
        self.roles_button = button(master_root, "Stage eleven personnel roles", "The game will fill this category's eleven lineup slots using these roles in every book on the disc.", self.stage_roles)
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
        self.side_picker.currentIndexChanged.connect(self._selection_changed)
        self.formation_picker.currentIndexChanged.connect(self._formation_changed)
        self.play_picker.currentIndexChanged.connect(self._play_changed)
        self.master_table.itemSelectionChanged.connect(self._master_changed)
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
            except (ValueError, RuntimeError, OSError, ImportError, AttributeError, KeyError, ValidationError) as exc:
                return None, str(exc)
        def complete(result):
            if generation != self._generation or source != self._source():
                return
            self._loading = False
            value, error = result
            if error:
                self.notice.setText(error)
            else:
                done(value)
            self._enable()
        self.run_task(label, work, complete, blocking)

    def _enable(self):
        ready = bool(getattr(self.facade, "source_ready", False))
        enabled = ready and not self._busy and not self._loading
        self.team_controls.setEnabled(enabled)
        self.preview_group.setEnabled(enabled)
        self.levers.setEnabled(enabled and self._context is not None)
        self.master_group.setEnabled(enabled and self._context is not None)
        self.review_group.setEnabled(enabled)
        self.confirm_button.setEnabled(enabled and self._review is not None and not self._review["refused"])
        self.undo_button.setEnabled(enabled)
        self.experiments.setEnabled(not self._busy and not self._loading)

    def set_busy(self, busy):
        self._busy = bool(busy)
        self.legacy.set_busy(busy)
        self._enable()

    def set_context(self, *_):
        self._generation += 1
        self._loading = False
        self._review = None
        self._context = None
        self._custom_timer.stop()
        self.grid.setRowCount(0)
        self.plan_table.setRowCount(0)
        self.coverage_table.setRowCount(0)
        self._enable()
        if getattr(self.facade, "source_ready", False):
            self.refresh()

    def _selection_changed(self, *_):
        if not self._updating:
            self._review = None
            self.plan_table.setRowCount(0)
            self.refresh()

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
        self.notice.setText("Recomputing calls from the staged book and team tendency…")
        # Copy Qt values before entering a worker.
        custom = {key: control.value() for key, control in self.custom.items()}
        custom["phase"] = "scrimmage"
        snapshot = self.facade.playcalling_snapshot()
        def operation(progress):
            context = self.facade.playcalling_context(team, side, progress)
            if side == "offense":
                rows = list(SITUATIONS) + [("Custom situation", custom)]
            else:
                rows = [(f"Offense row {i}: " + ", ".join(c.name for c in context["categories"] if c.row == i),
                         {"offense_category_row": i, "yards_to_goal": custom["yards_to_goal"]}) for i in range(11)]
            return context, self.facade.playcalling_predict(context, side, rows, progress)
        def done(result):
            if snapshot != self.facade.playcalling_snapshot():
                self.refresh()
                return
            self._context, predictions = result
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
        self._updating = True
        previous_form = self.formation_picker.currentData()
        previous_donor = self.donor_picker.currentText()
        self.team_picker.clear()
        for team in c["state"].teams:
            self.team_picker.addItem(team["team_name"], team["team_index"])
        self.team_picker.setCurrentIndex(self.team_picker.findData(c["team"]["team_index"]))
        self.book_label.setText(c["book"] + (", shared with " + ", ".join(c["sharing"]) if c["sharing"] else ", used only by this team") + ".")
        self.donor_picker.clear(); self.donor_picker.addItems(c["donors"])
        selected = previous_donor if previous_donor in c["donors"] else c["book"]
        self.donor_picker.setCurrentIndex(max(0, self.donor_picker.findText(selected)))
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
        self.master_table.selectRow(0)
        names = {r.id: r.name for r in c["categories"]}
        fill(self.receipt_table, [(e["request"]["kind"].replace("_", " "), e["request"].get("book", e["request"].get("team", "Every book / ownership")),
                                  e["before"], e["after"], ", ".join(names[i] for i in e["retired"])) for e in c["events"]])
        self._updating = False
        self._formation_changed()
        self._master_changed()

    def _formation_changed(self, *_):
        if self._updating or not self._context:
            return
        form = next((f for f in self._context["formations"] if f["id"] == self.formation_picker.currentData()), None)
        if form is None:
            return
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
        category = self._context["categories"][self.master_table.currentRow()]
        self.master_row.setValue(category.row)
        for i, control in enumerate(self.roles):
            role = self._context["state"].master[0x49 + category.id * 16 + i] & 31
            control.setCurrentIndex(control.findData(role))

    def _book_request(self, kind, **values):
        if not self._context:
            return None
        return {"kind": kind, "book": self._context["book"], **values}

    def review_request(self, request, confirm=False):
        if request is None:
            return
        self._review = None
        def done(review):
            self._review = review
            event = review["event"]
            names = review["category_names"]
            fill(self.coverage_table, [(row, ", ".join(names[i] for i in ids) or "None", "Covered" if ids else "No candidate") for row, ids in event["coverage"].items()])
            text = (event["warning"] or "The writer accepted this edit.") + " Retired categories: " + (", ".join(review["retired_names"]) or "none") + "."
            self.review_label.setText(text)
            self.notice.setText(text)
            if not confirm and not event["warning"]:
                self.confirm_review()
        self._task("Review CPU Play Calling edit", lambda p: self.facade.playcalling_review(request, p), done)

    def confirm_review(self):
        if self._review is None or self._review["refused"]:
            return
        review = self._review
        def done(_):
            self._review = None
            self.modifiedChanged.emit()
            self.refresh()
        self._task("Stage CPU Play Calling edit", lambda p: self.facade.stage_playcalling(review, p), done, True)

    def own_book(self, every):
        if not self._context:
            return
        side = self.side_picker.currentData()
        team = None if every else self.team_picker.currentData()
        donor = None if every else self.donor_picker.currentText()
        def done(request):
            fill(self.plan_table, [(r["team_name"], r["label_id"], r["donor_name"], r["clone_name"]) for r in request["assignments"]])
            self.review_request(request, True)
        self._task("Plan independent team books", lambda p: self.facade.playcalling_plan(side, team, donor, p), done)

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

    def retire(self):
        self.review_request(self._book_request("retire", category=self.retire_picker.currentData()), True)

    def stage_tendency(self):
        self.review_request({"kind": "tendency", "team": self.team_picker.currentData(), "value": self.tendency.value()})

    def stage_audibles(self):
        self.review_request(self._book_request("audibles"))

    def _category_id(self):
        row = self.master_table.currentRow()
        return self._context["categories"][row].id if row >= 0 and self._context else None

    def stage_master_row(self):
        if self._category_id() is not None:
            self.review_request({"kind": "master_row", "category": self._category_id(), "row": self.master_row.value()})

    def stage_roles(self):
        if self._category_id() is not None:
            self.review_request({"kind": "master_roles", "category": self._category_id(), "roles": [c.currentData() for c in self.roles]})

    def fix_52(self):
        if self._context:
            category = next((c.id for c in self._context["categories"] if c.name.replace(" ", "") in {"5-2", "52"}), None)
            if category is not None:
                self.review_request({"kind": "master_row", "category": category, "row": 13})

    def undo(self):
        def done(_):
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
