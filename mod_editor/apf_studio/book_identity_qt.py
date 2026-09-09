"""Standalone Playbooks workspace; protected gui.py integration is in WIRING.md.

All disk work uses the Studio's task runner. This operates on a selected built
game folder, so staged project edits must be built before clone finalization.
"""
from __future__ import annotations

import json
from pathlib import Path

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QAbstractItemView, QComboBox, QFileDialog, QFormLayout, QHBoxLayout,
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
        self.reviewed = None
        self._generation = 0
        layout = QVBoxLayout(self)
        title = QLabel("Book Identity and independent CPU books")
        title.setObjectName("panelTitle")
        layout.addWidget(title)
        note = QLabel(
            "Build your project first, then choose its game folder here. Review a "
            "scheme preset or give a team its own copy of an offensive book. "
            "Cloning is the final step: finish other Studio edits before cloning. "
            "Build creates a new folder with a verification receipt. Expanded "
            "books and CPU behavior remain UNWITNESSED in game. A loaded roster "
            "save can override these disc assignments."
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
        self.action.addItem("Independent offensive book", "clone")
        for slug in presets.PRESET_IDS:
            self.action.addItem(presets.load_preset(slug)["name"], slug)
        self.action.addItem("All three scheme presets", "all-presets")
        self.team = QComboBox()
        self.label = QComboBox()
        self.donor = QComboBox()
        for name in sorted(x for x in splb.STOCK_BOOKS.values() if x.startswith("O-")):
            self.donor.addItem(name, name)
        for caption, widget in (("Action", self.action), ("Team", self.team),
                                ("Unused offensive label", self.label), ("Copy this book", self.donor)):
            form.addRow(caption, widget)
        layout.addLayout(form)
        row = QHBoxLayout()
        self.review = QPushButton("Review change")
        self.build = QPushButton("Build new game folder…")
        row.addWidget(self.review)
        row.addWidget(self.build)
        self.stage = QPushButton("Stage scheme presets in project")
        self.revert_presets = QPushButton("Revert staged presets")
        self.stage.setVisible(facade is not None)
        self.revert_presets.setVisible(facade is not None)
        row.addWidget(self.stage)
        row.addWidget(self.revert_presets)
        self.stage.clicked.connect(self._stage_presets)
        self.revert_presets.clicked.connect(lambda: self._stage_presets(clear=True))
        layout.addLayout(row)
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
        cloning = self.action.currentData() == "clone"
        for box in (self.team, self.label, self.donor):
            box.setEnabled(cloning and self.source_index is not None)
        self.review.setEnabled(self.source_index is not None and
                               (not cloning or self.label.currentData() is not None))

    def set_context(self):
        ready = self.facade is not None and self.facade.source_ready and not self._busy
        self.stage.setEnabled(ready and self.action.currentData() != "clone")
        self.revert_presets.setEnabled(ready)

    refresh = set_context

    def set_busy(self, busy):
        self._busy = busy
        self.set_context()

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
            used = {team.offense for team in parsed.teams}
            for label in parsed.labels:
                if label.side == "offense" and label.index not in used:
                    self.label.addItem(f"{label.name} (currently {label.kind})", label.index)
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
        request = (clone.CloneRequest(self.label.currentData(), self.team.currentData(), self.donor.currentData())
                   if action == "clone" else None)
        slugs = presets.PRESET_IDS if action == "all-presets" else (action,)

        def work(progress):
            progress("Compiling and independently reparsing the selection", 0, 1)
            if request is not None:
                plan = clone.compile_unlock(source, [request])
                return action, plan, plan.report
            reports = [presets.compile_preset(source, presets.load_preset(x)).report for x in slugs]
            return action, tuple(slugs), {"presets": reports, "book_identity": reports[0]["book_identity"]}

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
            if action == "clone":
                return clone.build_new_folder(plan, destination, update)
            return presets.build_presets_folder(source, plan, destination, update,
                                                expected_reports=report["presets"])

        def built(result):
            if generation != self._generation:
                return
            self._invalidate()
            self.receipt.setPlainText(json.dumps(result, indent=2))
            self.status.setText(f"Verified new game: {destination}. In-game behavior is UNWITNESSED.")

        self.run_task("Building verified book folder", work, built, True)
