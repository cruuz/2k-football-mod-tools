"""Rosters Abilities page. EXPERIMENTAL / UNWITNESSED; parent wiring in WIRING.md."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Callable

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (QCheckBox, QComboBox, QFormLayout, QGroupBox, QHBoxLayout,
                            QLabel, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem,
                            QVBoxLayout, QWidget)

from mod_editor.core import nfl2k5_abilities_editor as editor
from mod_editor.core import nfl2k5_abilities_runtime as runtime


@dataclass
class AbilitiesEdit:
    label: str
    receipt: dict
    undo: Callable[[], None]
    redo: Callable[[], None]


class AbilitiesPanel(QWidget):
    edit_committed = pyqtSignal(object)  # already applied; push onto Rosters shared undo
    lock_settings_changed = pyqtSignal(object)  # pass to the Build settings owner

    def __init__(self, parent=None):
        super().__init__(parent)
        self.document = None
        self.player = None
        self._loading = False
        self._preview = None
        self.last_receipt = None
        layout = QVBoxLayout(self)
        note = QLabel(
            "EXPERIMENTAL / UNWITNESSED. Retail ignores these ability flags. Patch: "
            "Player abilities rules v2 supplies move locks and small live rating bonuses. "
            "Star, Superstar and X-Factor allow 2, 4 and 7 abilities. Their bonuses are "
            "2, 4 and 6 effective points, capped at 100. The cosmetic star stays separate. "
            "Lowering a tier removes excess abilities in the order shown. Rosters Undo restores them.")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.player_label = QLabel("Select a player in Rosters")
        layout.addWidget(self.player_label)
        form = QFormLayout()
        self.tier_combo = QComboBox()
        self.tier_combo.addItems(editor.TIERS)
        self.tier_combo.currentIndexChanged.connect(self._tier_changed)
        form.addRow("Ability tier", self.tier_combo)
        layout.addLayout(form)
        self.ability_checks = {}
        for name, label in editor.LABELS.items():
            check = QCheckBox(label)
            if name in runtime.EFFECTS:
                check.setToolTip(f"Stored {name.replace('_', ' ')} permission plus a tier bonus to "
                                 f"{runtime.EFFECTS[name][2]} during live play. No guaranteed outcome.")
            check.toggled.connect(lambda enabled, key=name: self._ability_changed(key, enabled))
            self.ability_checks[name] = check
            layout.addWidget(check)
        self.capacity_label = QLabel()
        layout.addWidget(self.capacity_label)

        locks = QGroupBox("Rules for the next disc build")
        lock_layout = QVBoxLayout(locks)
        self.lock_checks = {}
        for name, caption in (
            ("lock_right_stick", "Lock right-stick moves behind the ability"),
            ("lock_special_moves", "Lock special moves behind their abilities"),
            ("lock_speedster", "Lock Speedster speed"),
        ):
            check = QCheckBox(caption)
            check.setChecked(True)
            check.toggled.connect(self._locks_changed)
            self.lock_checks[name] = check
            lock_layout.addWidget(check)
        lock_note = QLabel(
            "Turn both move locks off to keep the retail charge meter for every action. "
            "With either move lock on, only live carriers and known moves may use charge. "
            "Turning a lock off does not grant a rating bonus. Rebuild the disc to change rules.")
        lock_note.setWordWrap(True)
        lock_layout.addWidget(lock_note)
        layout.addWidget(locks)

        assignment = QGroupBox("Assign abilities by ratings")
        assign_layout = QVBoxLayout(assignment)
        explanation = QLabel(
            "Replace tiers and abilities for active NFL club players across the league. "
            "Rank 1 per position becomes X-Factor, the next third Superstar, the rest Star. "
            "Players outside the top N become Unranked. Free agents and draft templates stay. "
            "Review the list before applying. One Rosters Undo restores the whole pass.")
        explanation.setWordWrap(True)
        assign_layout.addWidget(explanation)
        buttons = QHBoxLayout()
        buttons.addWidget(QLabel("Top N per position"))
        self.top_n = QSpinBox()
        self.top_n.setRange(1, 100)
        self.top_n.setValue(10)
        self.top_n.valueChanged.connect(self._clear_preview)
        buttons.addWidget(self.top_n)
        self.preview_button = QPushButton("Preview assignment")
        self.preview_button.clicked.connect(self.preview_assignment)
        buttons.addWidget(self.preview_button)
        self.apply_button = QPushButton("Apply assignment")
        self.apply_button.clicked.connect(self.apply_assignment)
        buttons.addWidget(self.apply_button)
        assign_layout.addLayout(buttons)
        self.preview_table = QTableWidget(0, 4)
        self.preview_table.setHorizontalHeaderLabels(("Player", "Position", "Tier", "Abilities"))
        self.preview_table.setEditTriggers(QTableWidget.NoEditTriggers)
        assign_layout.addWidget(self.preview_table)
        layout.addWidget(assignment)
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        layout.addStretch()
        self.set_document(None)

    def set_document(self, document):
        self.document = document
        self.player = None
        self.last_receipt = None
        self._clear_preview()
        self.preview_button.setEnabled(document is not None)
        self.set_player(None)
        self.status_label.clear()

    def set_player(self, player):
        if player is not None and (self.document is None or
                                   not any(p is player for p in self.document.players)):
            raise editor.AssignmentError("selected player is not in this roster")
        self.player = player
        self._loading = True
        try:
            self.player_label.setText(player.display if player else "Select a player in Rosters")
            tier = player.record.ability_tier if player else 0
            self.tier_combo.setCurrentIndex(tier)
            self.tier_combo.setEnabled(player is not None)
            for name, check in self.ability_checks.items():
                check.setChecked(bool(player and player.record.abilities[name]))
                check.setEnabled(player is not None)
            used = sum(player.record.abilities.values()) if player else 0
            message = f"{used} of {editor.LIMITS[tier]} ability slots used"
            if used > editor.LIMITS[tier]:
                message += ". Existing flags preserved. Choose a tier before editing."
            self.capacity_label.setText(message)
        finally:
            self._loading = False

    def set_lock_settings(self, settings):
        values = runtime._locks(**settings)
        self._loading = True
        try:
            for name, value in values.items():
                self.lock_checks[name].setChecked(value)
        finally:
            self._loading = False

    def lock_settings(self):
        return {name: check.isChecked() for name, check in self.lock_checks.items()}

    def _locks_changed(self, _enabled):
        if not self._loading:
            self.lock_settings_changed.emit(self.lock_settings())

    def _clear_preview(self, *_):
        self._preview = None
        self.apply_button.setEnabled(False)
        self.preview_table.setRowCount(0)

    def _commit(self, plan, label):
        document = self.document
        receipt = editor.apply_plan(document, plan, require_fresh=True)
        self.last_receipt = receipt
        self._clear_preview()
        self.set_player(self.player)
        if not receipt["changed_players"]:
            self.status_label.setText("No abilities changed.")
            return receipt

        def replay(reverse):
            if self.document is not document:
                raise editor.AssignmentError("this edit belongs to a different roster")
            editor.apply_plan(document, plan, reverse=reverse)
            self._clear_preview()
            self.set_player(self.player)

        self.edit_committed.emit(AbilitiesEdit(label, receipt, lambda: replay(True), lambda: replay(False)))
        self.status_label.setText(f"Updated {receipt['changed_players']} players. Rosters Undo restores this edit.")
        return receipt

    def _tier_changed(self, tier):
        if not self._loading and self.player is not None:
            self._edit_player(tier, editor.fit_tier(self.player.record, tier))

    def _ability_changed(self, name, enabled):
        if not self._loading and self.player is not None:
            abilities = dict(self.player.record.abilities)
            abilities[name] = enabled
            self._edit_player(self.player.record.ability_tier, [n for n, v in abilities.items() if v])

    def _edit_player(self, tier, abilities):
        try:
            self._commit(editor.plan_player(self.document, self.player, tier=tier, abilities=abilities), "Abilities")
        except editor.AssignmentError as exc:
            self.set_player(self.player)
            self.status_label.setText(str(exc))

    def preview_assignment(self):
        if self.document is None:
            return
        try:
            plan = editor.plan_auto_assign(self.document, top_n=self.top_n.value())
            self._clear_preview()
            self._preview = plan
            changed = [row for row in plan["rows"] if row["mask"]]
            self.preview_table.setRowCount(len(changed))
            for index, row in enumerate(changed):
                identity = row["identity"]
                values = (f"{identity['first']} {identity['last']}", row["position"], row["tier"],
                          ", ".join(editor.LABELS[n] for n in row["abilities"]))
                for column, value in enumerate(values):
                    self.preview_table.setItem(index, column, QTableWidgetItem(value))
            self.apply_button.setEnabled(bool(changed))
            self.status_label.setText(f"Preview: {len(changed)} players would change.")
        except editor.AssignmentError as exc:
            self._clear_preview()
            self.status_label.setText(str(exc))

    def apply_assignment(self):
        if self._preview is None:
            return
        try:
            self._commit(self._preview, "Assign abilities by ratings")
        except editor.AssignmentError as exc:
            self._clear_preview()
            self.status_label.setText(str(exc))

    def save_receipt(self, path):
        if self.last_receipt is None:
            raise editor.AssignmentError("no ability edit to export")
        with Path(path).resolve().open("x", encoding="utf-8") as output:
            json.dump(self.last_receipt, output, indent=2)
            output.write("\n")
