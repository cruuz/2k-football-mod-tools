"""Reviewable APFe batch mapping dialog; game writes remain in existing pages."""
from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QHeaderView, QLabel,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QHBoxLayout, QFileDialog, QMenu, QMessageBox, QPushButton,
)

from .ps3_texture_bundle import (Assignment, BundleError, build_plan, destination_slots, read_bundle,
                                 stage_plan, measure_bundle_logos, logo_fit_row)
from .helmet_crest_design import CREST_SIMPLIFICATION_HELP
from .apf_theme import fit_dialog


class Ps3BundleMappingDialog(QDialog):
    """Select imported pairs and explicit destination slots before staging.

    Construct after a worker has read the bundle and live slot inventory.
    ``plan`` is populated only by a valid Accept. Rejected pairs are displayed
    in the summary but cannot enter the mapping. No game/session mutation
    occurs in this dialog.
    """
    def __init__(self, bundle, slots, *, measurements=None, kind=None, parent=None):
        super().__init__(parent)
        self.bundle = bundle
        self.slots = tuple(slots)
        self.plan = None
        self.measurements = measurements or {}
        self.setWindowTitle("Import PS3 bundle — assign teams")
        self.resize(1060, 600)
        layout = QVBoxLayout(self)
        summary = QLabel("Choose pairs and destination slots. Both layers stay together.")
        summary.setToolTip(
            "Team colors are controlled by the game palette. "
            "Logo and endzone builds regenerate mip levels; endzones may simplify colors or reduce resolution to fit. "
            "Every build must still fit its fixed allocation. In-game result: UNWITNESSED."
        )
        summary.setWordWrap(True)
        layout.addWidget(summary)
        self.message = QLabel()
        self.message.setObjectName("validationBanner")
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        self.allow_simplification = QCheckBox("Allow crest shade reduction to fit")
        self.allow_simplification.setChecked(True)
        self.allow_simplification.setToolTip(CREST_SIMPLIFICATION_HELP)
        layout.addWidget(self.allow_simplification)
        toolbar = QHBoxLayout()
        self.select_matched_button = QPushButton("Select all matched")
        self.clear_button = QPushButton("Clear")
        self.resolve_button = QPushButton("Next free matching slot")
        self.room_button = QPushButton("Choose packages with room")
        self.room_button.setToolTip("Explicitly assign checked logo rows to packages with room; review the new slot numbers before staging because the roster crest index must match.")
        for button in (self.select_matched_button, self.clear_button, self.resolve_button, self.room_button):
            button.setObjectName("utilityButton")
            toolbar.addWidget(button)
        toolbar.addStretch(1)
        layout.addLayout(toolbar)
        if bundle.rejected_pairs:
            rejected = QLabel("Rejected pairs: " + "; ".join(
                f"{r['team']} {r['kind']}: {r['reason']}" for r in bundle.rejected_pairs))
            rejected.setWordWrap(True)
            layout.addWidget(rejected)
        pairs = [p for p in bundle.pairs if kind is None or p.kind == kind]
        self.table = QTableWidget(len(pairs), 5)
        self.table.setHorizontalHeaderLabels(("Import", "Source team / pair", "Variant", "Xbox 360 destination", "Compressed art fit"))
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.setColumnWidth(0, 60)
        self.table.setColumnWidth(1, 230)
        self.table.setColumnWidth(2, 140)
        self.table.setColumnWidth(3, 320)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.rows = []
        for number, pair in enumerate(pairs):
            enabled = QCheckBox()
            choices = QComboBox()
            choices.addItem("Choose destination…", None)
            matching = []
            for slot in self.slots:
                if slot.kind == pair.kind and slot.writable:
                    label = (f"Logo slot {slot.crest_asset_index}: {slot.label} · {slot.compressed_art_budget:,} bytes"
                             if slot.compressed_art_budget is not None else f"{slot.label} · {slot.slot_id}")
                    choices.addItem(label, slot.slot_id)
                    if slot.entry_hash == pair.entry_hash:
                        matching.append(choices.count() - 1)
            if len(matching) == 1:
                choices.setCurrentIndex(matching[0])
                enabled.setChecked(True)
            self.table.setCellWidget(number, 0, enabled)
            for column, text in ((1, f"{pair.team} — {pair.kind}"), (2, pair.variant + (f" / {pair.entry_hash:08x}" if pair.entry_hash is not None else ""))):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(number, column, item)
            self.table.setCellWidget(number, 3, choices)
            item = QTableWidgetItem()
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(number, 4, item)
            self.rows.append((pair, enabled, choices))
            enabled.toggled.connect(self._validate)
            choices.currentIndexChanged.connect(self._validate)
        layout.addWidget(self.table)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Stage selected pairs")
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setObjectName("primaryButton")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.select_matched_button.clicked.connect(self._select_matched)
        self.clear_button.clicked.connect(self._clear)
        self.resolve_button.clicked.connect(self._resolve_collisions)
        self.room_button.clicked.connect(self._choose_room)
        self.allow_simplification.toggled.connect(self._validate)
        self._validate()
        fit_dialog(self)

    def _clear(self):
        for _pair, enabled, _choices in self.rows:
            enabled.setChecked(False)

    def _select_matched(self):
        for pair, enabled, choices in self.rows:
            matches = [slot for slot in self.slots if slot.writable and slot.kind == pair.kind
                       and slot.entry_hash == pair.entry_hash]
            if len(matches) == 1:
                choices.setCurrentIndex(choices.findData(matches[0].slot_id))
                enabled.setChecked(True)
        self._validate()

    def _resolve_collisions(self):
        """Explicitly allocate repeated destinations to the next writable family slot."""
        used = set()
        for pair, enabled, choices in self.rows:
            if not enabled.isChecked():
                continue
            chosen = choices.currentData()
            if chosen is None or chosen in used:
                candidates = [slot for slot in self.slots if slot.writable and slot.kind == pair.kind
                              and slot.slot_id not in used]
                candidates.sort(key=lambda slot: (slot.entry_hash != pair.entry_hash, slot.outer_index))
                if candidates:
                    choices.setCurrentIndex(choices.findData(candidates[0].slot_id))
                    chosen = choices.currentData()
            if chosen is not None:
                used.add(chosen)
        self._validate()

    def _make_plan(self):
        assignments = []
        for pair, enabled, choices in self.rows:
            if enabled.isChecked():
                if choices.currentData() is None:
                    raise BundleError(f"Choose a destination for {pair.team} {pair.kind}")
                assignments.append(Assignment(pair.pair_id, choices.currentData()))
        plan = build_plan(self.bundle, self.slots, assignments, measurements=self.measurements,
                          allow_simplification=self.allow_simplification.isChecked())
        for (pair, slot), row in zip(plan.assignments, plan.receipt["assignments"]):
            if pair.kind == "logo" and slot.compressed_art_budget is not None and row["fit"]["fits"] is not True:
                raise BundleError(row["fit"].get("refusal") or row["fit"]["status"])
        return plan

    def _choose_room(self):
        used = set()
        for pair, enabled, choices in self.rows:
            if not enabled.isChecked():
                continue
            if pair.kind != "logo":
                used.add(choices.currentData())
                continue
            candidates = [slot for slot in self.slots if slot.kind == "logo" and slot.writable
                          and slot.slot_id not in used and slot.compressed_art_budget is not None]
            candidates.sort(key=lambda slot: (-slot.compressed_art_budget, slot.crest_asset_index))
            for slot in candidates:
                fit = logo_fit_row(pair, slot, self.slots, self.measurements,
                                   allow_simplification=self.allow_simplification.isChecked())
                if fit["fits"] is True:
                    choices.setCurrentIndex(choices.findData(slot.slot_id))
                    used.add(slot.slot_id)
                    break
        self._validate()

    def _validate(self, *_args):
        by_id = {slot.slot_id: slot for slot in self.slots}
        for number, (pair, _enabled, choices) in enumerate(self.rows):
            slot = by_id.get(choices.currentData())
            item = self.table.item(number, 4)
            if slot is None:
                item.setText("Choose a destination")
                item.setToolTip("")
                continue
            try:
                fit = logo_fit_row(pair, slot, self.slots, self.measurements,
                                   allow_simplification=self.allow_simplification.isChecked())
                item.setText(fit["status"])
                rooms = fit.get("packages_with_room", ())
                detail = (f"{fit['compressed_art_bytes']:,} bytes used / {fit['budget_bytes']:,} available. "
                          if "budget_bytes" in fit else "")
                tooltip = detail + "Packages with room: " + ("; ".join(
                    f"Logo slot {row['slot']} ({row['budget_bytes']:,} bytes, {row['shades_per_region']} shades)"
                    for row in rooms) or "none measured")
                item.setToolTip(tooltip)
                choices.setToolTip(tooltip + "\nThe roster crest index must match the slot you choose.")
            except BundleError as exc:
                item.setText(str(exc))
        try:
            plan = self._make_plan()
            self.message.setText(f"{len(plan.assignments)} pairs / {len(plan.items)} textures ready to stage. Build verification remains required.")
            valid = True
        except BundleError as exc:
            self.message.setText(str(exc))
            valid = False
        self.message.setProperty("valid", valid)
        self.message.style().unpolish(self.message)
        self.message.style().polish(self.message)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(valid)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setToolTip(self.message.text())

    def accept(self):
        try:
            self.plan = self._make_plan()
        except BundleError:
            self._validate()
            return
        super().accept()


def import_button(parent, facade, run_task, on_staged, *, kind=None):
    """Ready-to-wire button; callbacks/Qt stay on the UI thread.

    ``on_staged(plan, modifications)`` refreshes the owning page. Inventory
    and staging run through its existing worker runner, under the facade's
    session lock for mutation. A source switch invalidates pending review.
    """
    button = QPushButton("Import PS3 bundle…", parent)
    menu = QMenu(button)
    button.setMenu(menu)

    def choose(folder):
        if not facade.source_ready:
            QMessageBox.information(parent, "Load APF first", "Load your Xbox 360 APF game before assigning PS3 textures.")
            return
        selected = (QFileDialog.getExistingDirectory(parent, "Choose APFe team folder or NFL Logos folder") if folder
                    else QFileDialog.getOpenFileName(parent, "Choose APFe texture bundle", "", "ZIP bundles (*.zip)")[0])
        if not selected:
            return
        session = facade.require_session()

        def inspect(progress):
            progress("Reading PS3 texture bundle", 0, 2)
            bundle = read_bundle(Path(selected))
            progress("Resolving Xbox 360 texture slots", 1, 2)
            slots = destination_slots(session.source.index_0a)
            measurements = (measure_bundle_logos(bundle, slots, session.source.index_0a, progress)
                            if kind in (None, "logo") else {})
            progress("Bundle ready to review", 2, 2)
            return bundle, slots, measurements

        def review(result):
            if facade.session is not session:
                QMessageBox.information(parent, "Game source changed", "Import the bundle again against the selected game.")
                return
            bundle, slots, measurements = result
            dialog = Ps3BundleMappingDialog(bundle, slots, measurements=measurements, kind=kind, parent=parent)
            if dialog.exec_() != QDialog.Accepted:
                return
            plan = dialog.plan

            def stage(progress):
                with facade._session_lock:
                    if facade.require_session() is not session:
                        raise BundleError("Game source changed during bundle review")
                    progress("Staging PS3 texture pairs", 0, 1)
                    modifications = stage_plan(session, plan)
                    for modification in modifications:
                        if modification.kind == "helmet_crest_design":
                            facade._staged_team_logo_png = modification.replacement_path
                        elif modification.kind == "field_art_texture":
                            meta = modification.metadata
                            facade._staged_field_art[(meta["entry_index"], meta["file_index"])] = modification.replacement_path
                    facade.last_build = None
                    progress("PS3 texture pairs staged", 1, 1)
                    return modifications
            def staged(modifications):
                if facade.session is session:
                    on_staged(plan, modifications)
            run_task("Staging PS3 bundle", stage, staged, True)
        run_task("Reading PS3 bundle", inspect, review, True)

    menu.addAction("Choose ZIP…", lambda: choose(False))
    menu.addAction("Choose folder…", lambda: choose(True))
    return button
