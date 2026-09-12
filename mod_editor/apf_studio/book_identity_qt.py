"""Standalone Playbooks workspace; protected gui.py integration is in WIRING.md.

All disk work uses the Studio's task runner. This operates on a selected built
game folder, so staged project edits must be built before clone finalization.
"""
from __future__ import annotations

import json
from pathlib import Path

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout,
    QLabel, QPlainTextEdit, QPushButton, QTableWidget, QTableWidgetItem,
    QTabWidget, QVBoxLayout, QWidget,
)

from mod_editor.core import apf2k8_book_clone as clone
from mod_editor.core import apf2k8_book_identity as identity
from mod_editor.core import apf2k8_scheme_presets as presets
from mod_editor.core import apf2k8_splb_writer as splb
from mod_editor.core.errors import ValidationError


class BookIdentityPanel(QWidget):
    """Review serialized sharing, then build one clone or a scheme selection."""

    modifiedChanged = pyqtSignal()

    def __init__(self, run_task, *, facade=None):
        super().__init__()
        self.run_task = run_task
        self.facade = facade
        self._busy = False
        self.source_index = None
        self._identity = None
        self.reviewed = None
        self._generation = 0
        layout = QVBoxLayout(self)
        title = QLabel("Book Identity and independent CPU books")
        title.setObjectName("panelTitle")
        layout.addWidget(title)
        note = QLabel(
            "Give one team its own book, then edit its formations, plays and audibles in Fine-tune. "
            "Team chooses who uses the copy. Unused label names that copy; the game resolves the label's "
            "book name to its contents. Copy this book chooses the starting formations and plays. "
            "Other teams keep their shared book. A loaded roster save can override these disc assignments.\n\n"
            "1. Build your current Studio project and choose that game folder here. "
            "2. Choose a team, unused label and starting book, then Review and Build new game folder. "
            "Cloning inserts an archive entry and shifts entry numbers, so the old Studio project must be "
            "finished first. 3. Open the new folder with Edit books in Fine-tune below; save its book-edit "
            "recipe and build another new folder. This editor resolves the shifted entries by name. "
            "Expanded books and CPU behavior remain UNWITNESSED in game."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        source_row = QHBoxLayout()
        self.choose = QPushButton("Choose built game folder…")
        self.source_label = QLabel("No game selected")
        self.source_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        source_row.addWidget(self.choose)
        source_row.addWidget(self.source_label, 1)
        layout.addLayout(source_row)
        form = QFormLayout()
        self.action = QComboBox()
        self.action.addItem("Copy the book as it is", "clone")
        for slug in presets.PRESET_IDS:
            self.action.addItem(presets.load_preset(slug)["name"], slug)
        self.team = QComboBox()
        self.label = QComboBox()
        self.donor = QComboBox()
        for name in sorted(splb.BOOK_SIDES):
            self.donor.addItem(name, name)
        for caption, widget in (("Starting content recipe", self.action), ("Team using this copy", self.team),
                                ("Unused label on this side", self.label), ("Copy this book", self.donor)):
            form.addRow(caption, widget)
        layout.addLayout(form)
        self.recipe_note = QLabel("No recipe: copies the selected book's current content. You can edit the copy in Fine-tune.")
        self.recipe_note.setWordWrap(True)
        layout.addWidget(self.recipe_note)
        row = QHBoxLayout()
        self.review = QPushButton("Review change")
        self.build = QPushButton("Build new game folder…")
        row.addWidget(self.review)
        row.addWidget(self.build)
        self.stage = QPushButton("Stage recipe on shared stock book")
        self.revert_presets = QPushButton("Revert staged presets")
        self.stage.setVisible(facade is not None)
        self.revert_presets.setVisible(facade is not None)
        row.addWidget(self.stage)
        row.addWidget(self.revert_presets)
        self.stage.clicked.connect(self._stage_presets)
        self.revert_presets.clicked.connect(lambda: self._stage_presets(clear=True))
        layout.addLayout(row)
        self.edit = QPushButton("Edit books in Fine-tune…")
        self.edit.setToolTip("Open the chosen or newly built folder's stock and independent books. Save a book-edit recipe, then build a new folder.")
        self.edit.clicked.connect(self.open_fine_tune)
        self._edit_index = None
        self._edit_name = None
        self._content_dialogs = []
        layout.addWidget(self.edit)
        self.status = QLabel("Choose a game to inspect all 40 teams and their shared books.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        tabs = QTabWidget()
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Team", "Side", "Label", "Real book", "Other teams", "Proof"])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.receipt = QPlainTextEdit()
        self.receipt.setReadOnly(True)
        tabs.addTab(self.table, "Book Identity")
        tabs.addTab(self.receipt, "Review receipt")
        layout.addWidget(tabs, 1)
        boundary = QLabel(identity.FORMATION_PERSONNEL_BOUNDARY)
        boundary.setWordWrap(True)
        layout.addWidget(boundary)
        self.choose.clicked.connect(self._choose_source)
        self.review.clicked.connect(self.review_selection)
        self.build.clicked.connect(self._choose_output)
        self.action.currentIndexChanged.connect(self._fill_recipe)
        self.donor.currentIndexChanged.connect(self._donor_changed)
        for box in (self.action, self.team, self.label, self.donor):
            box.currentIndexChanged.connect(self._invalidate)
        self._invalidate()

    def _invalidate(self, *_args):
        self._generation += 1
        self.reviewed = None
        self.build.setEnabled(False)
        if self.source_index is not None:
            self.status.setText("Select an action and review its current result before building.")
        self.set_context()
        ready = self.source_index is not None and not self._busy
        for box in (self.team, self.label, self.donor):
            box.setEnabled(ready)
        self.review.setEnabled(ready and self.label.currentData() is not None)
        self.edit.setEnabled(not self._busy and (self._edit_index is not None or self.source_index is not None))

    def _fill_recipe(self, *_args):
        slug = self.action.currentData()
        if slug == "clone":
            self.recipe_note.setText("No recipe: copies the selected book's current content. Edit the copy in Fine-tune.")
            return
        recipe = presets.load_preset(slug)
        self.donor.blockSignals(True)
        self.donor.setCurrentIndex(self.donor.findData(recipe["book_type"]))
        self.donor.blockSignals(False)
        self._fill_labels()
        self.recipe_note.setText(
            f"{recipe['name']}: {recipe['intent']} Starts from {recipe['book_type']}; "
            "fills the copy's play membership and audible slots. Team and label remain editable. "
            "Choosing a different starting book clears this recipe. After building, change any "
            "formation, play or audible in Fine-tune. This changes book content, not play-calling logic. "
            + recipe['limitations'])

    def _donor_changed(self, *_args):
        self._fill_labels()
        slug = self.action.currentData()
        if slug != "clone" and presets.load_preset(slug)["book_type"] != self.donor.currentData():
            self.action.setCurrentIndex(0)

    def _fill_labels(self):
        selected = self.label.currentData()
        self.label.clear()
        if self._identity is None:
            return
        side = splb.BOOK_SIDES[self.donor.currentData()]
        used = {getattr(team, side) for team in self._identity.teams}
        for label in self._identity.labels:
            if label.side == side and label.index not in used:
                self.label.addItem(f"{label.name} (currently {label.kind})", label.index)
        if self.label.findData(selected) >= 0:
            self.label.setCurrentIndex(self.label.findData(selected))

    def set_context(self):
        ready = self.facade is not None and self.facade.source_ready and not self._busy
        self.stage.setEnabled(ready and self.action.currentData() != "clone")
        self.revert_presets.setEnabled(ready)

    refresh = set_context

    def set_busy(self, busy):
        self._busy = busy
        for dialog in self._content_dialogs:
            dialog.setEnabled(not busy)
        self.set_context()
        for widget in (self.choose, self.action, self.team, self.label, self.donor, self.review, self.build, self.edit):
            widget.setEnabled(not busy and (widget in (self.choose, self.action) or self.source_index is not None))
        self.build.setEnabled(not busy and self.reviewed is not None)
        self.review.setEnabled(not busy and self.source_index is not None and self.label.currentData() is not None)

    def _stage_presets(self, _checked=False, *, clear=False):
        selected = self.action.currentData()
        ids = () if clear else presets.PRESET_IDS if selected == "all-presets" else (selected,)
        session = self.facade.session
        snapshot = tuple(session.modifications)
        def work(progress):
            with self.facade._session_lock:
                if self.facade.session is not session or tuple(session.modifications) != snapshot:
                    raise ValidationError("The source/project changed before preset staging; review it again.")
                return self.facade.apply_scheme_presets(ids, progress)
        def complete(reports):
            self.receipt.setPlainText(json.dumps(reports, indent=2, sort_keys=True))
            self.status.setText("Scheme presets staged after current CPU edits. Build the complete project. "
                                "Presets own membership/tags in their recipe records. Gameplay UNWITNESSED.")
            self.modifiedChanged.emit()
        self.run_task("Staging scheme presets", work, complete, True)

    def _choose_source(self):
        folder = QFileDialog.getExistingDirectory(self, "Choose built APF game folder")
        if folder:
            self.load_path(Path(folder) / "0A")

    def load_path(self, index_path: Path):
        self.source_index = None
        self._edit_index = None
        self._edit_name = None
        self.edit.setText("Edit books in Fine-tune…")
        self.table.setRowCount(0)
        self.receipt.clear()
        self.source_label.setText("Inspecting selected game…")
        self._invalidate()
        generation = self._generation
        index_path = Path(index_path).resolve()

        def work(progress):
            progress("Reparsing team labels and real book resources", 0, 1)
            parsed = identity.parse_roster_identity(identity.read_disc_roster(index_path))
            report = identity.disc_book_identity_report(index_path)
            return index_path, parsed, report

        def loaded(result):
            if generation != self._generation:
                return
            self.source_index, parsed, report = result
            self.source_label.setText(str(self.source_index.parent))
            self.team.clear()
            self.label.clear()
            for team in parsed.teams:
                self.team.addItem(f"{team.index}: {team.name}", team.index)
            self._identity = parsed
            self._fill_labels()
            self._show_identity(report)
            self.receipt.setPlainText(json.dumps(report, indent=2))
            self.status.setText("Assignments reparsed. Select an action and review its result.")
            self._invalidate()

        self.run_task("Inspecting Book Identity", work, loaded, True)

    def _show_identity(self, report):
        self.table.setRowCount(len(report["assignments"]))
        for index, row in enumerate(report["assignments"]):
            values = [row["team_name"], row["side"], row["label"], row["resolved_book"] or "UNKNOWN",
                      ", ".join(str(x) for x in row["shared_with_team_indices"]) or "None", row["status"]]
            for column, value in enumerate(values):
                self.table.setItem(index, column, QTableWidgetItem(value))
        self.table.resizeColumnsToContents()

    def review_selection(self):
        if self.source_index is None:
            return
        self._invalidate()
        generation, source, action = self._generation, self.source_index, self.action.currentData()
        request = clone.CloneRequest(self.label.currentData(), self.team.currentData(), self.donor.currentData())
        slugs = () if action == "clone" else (action,)

        def work(progress):
            progress("Compiling and independently reparsing the team book copy", 0, 1)
            plan = clone.compile_unlock(source, [request], preset_ids=slugs)
            return action, plan, plan.report

        def reviewed(result):
            if generation != self._generation:
                return
            self.reviewed = result
            self.receipt.setPlainText(json.dumps(result[2], indent=2))
            self._show_identity(result[2]["book_identity"])
            self.build.setEnabled(True)
            self.status.setText("Offline reparse and allocation checks passed. Ready to build a new folder. "
                                "In-game behavior remains UNWITNESSED.")

        self.run_task("Reviewing book change", work, reviewed, True)

    def _choose_output(self):
        if self.reviewed is None:
            return
        selected, _filter = QFileDialog.getSaveFileName(self, "Name a new game folder", "APF-book-build")
        if selected:
            self.build_to(Path(selected))

    def build_to(self, destination: Path):
        if self.reviewed is None or self.source_index is None:
            raise ValidationError("Review the current book selection before building")
        action, plan, report = self.reviewed
        source, generation = self.source_index, self._generation
        self.build.setEnabled(False)

        def work(progress):
            update = lambda message: progress(message, 0, 1)
            return clone.build_new_folder(plan, destination, update)

        def built(result):
            if generation != self._generation:
                return
            self._edit_index = Path(destination) / "0A"
            bindings = report.get("roster_binding", {}).get("changes", [])
            self._edit_name = bindings[0]["after_type"] if bindings else None
            self._invalidate()
            self.receipt.setPlainText(json.dumps(result, indent=2))
            self.edit.setText("Edit the new independent book in Fine-tune…")
            self.status.setText(f"Verified new game: {destination}. Use Edit the new independent book in Fine-tune next. "
                                "In-game behavior is UNWITNESSED.")

        self.run_task("Building verified book folder", work, built, True)

    def open_fine_tune(self):
        index = self._edit_index or self.source_index
        if index is None:
            return
        from .book_content import BookContentSession
        generation = self._generation
        def loaded(session):
            if generation != self._generation:
                return
            dialog = BookContentDialog(session, self.run_task, self, self._edit_name)
            self._content_dialogs.append(dialog)
            dialog.finished.connect(lambda _result: self._content_dialogs.remove(dialog))
            dialog.show()
        self.run_task("Opening books by name", lambda _progress: BookContentSession(index), loaded, True)


class BookContentDialog(QDialog):
    def __init__(self, session, run_task, parent=None, selected_name=None):
        super().__init__(parent)
        from .playbook_membership_qt import ApfPlaybookMembershipPanel
        self.setWindowTitle("Fine-tune CPU books in this game folder")
        self.resize(1120, 800)
        self.session = session
        layout = QVBoxLayout(self)
        note = QLabel(f"{session.source.index_0a.parent}\nEdits belong to this folder. Save a book-edit recipe to continue later; "
                      "Build writes a separate new game folder with every edited book. The source stays unchanged.")
        note.setWordWrap(True)
        layout.addWidget(note)
        def content_task(title, work, callback, blocking):
            self.setEnabled(False)
            def completed(result):
                try:
                    callback(result)
                finally:
                    self.setEnabled(True)
            started = run_task(title, work, completed, blocking)
            if started is False:
                self.setEnabled(True)
            return started
        self.panel = ApfPlaybookMembershipPanel(session, content_task)
        layout.addWidget(self.panel)
        if selected_name:
            for outer, name in session.book_choices.items():
                if name == selected_name:
                    self.panel.book_picker.setCurrentIndex(self.panel.book_picker.findData(outer))
                    break
        row = QHBoxLayout()
        save = QPushButton("Save book-edit recipe…")
        load = QPushButton("Open book-edit recipe…")
        row.addWidget(save)
        row.addWidget(load)
        layout.addLayout(row)
        def save_recipe():
            path, _ = QFileDialog.getSaveFileName(self, "Save book edits", "book-edits.json", "JSON (*.json)")
            if path:
                content_task("Saving book edits", lambda _progress: session.save_recipe(path), lambda _result: None, True)
        def load_recipe():
            path, _ = QFileDialog.getOpenFileName(self, "Open book edits", "", "JSON (*.json)")
            if path:
                content_task("Opening book edits", lambda _progress: session.load_recipe(path),
                         lambda _result: self.panel.set_context(), True)
        save.clicked.connect(save_recipe)
        load.clicked.connect(load_recipe)
