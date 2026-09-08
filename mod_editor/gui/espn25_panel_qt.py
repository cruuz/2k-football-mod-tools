"""Hostable ESPN Anniversary tab. EXPERIMENTAL / UNWITNESSED.

Only the protected Rosters-tab mount and BuildPlan handoff remain in WIRING.md.
The table uses the existing roster CSV codec, with historic-file restrictions.
"""
from __future__ import annotations

import csv
import io
import json
from pathlib import Path

from PyQt5 import QtCore, QtWidgets

from mod_editor.core import nfl2k5_espn25_scenarios as espn


class Espn25Panel(QtWidgets.QWidget):
    plan_ready = QtCore.pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.catalog = None
        self.pending = {}
        self.current = None
        self.loading = False
        layout = QtWidgets.QVBoxLayout(self)
        note = QtWidgets.QLabel(
            "ESPN Anniversary: EXPERIMENTAL / UNWITNESSED\n"
            "Edit the historic players used by each moment. Changes also affect this historic team "
            "outside Anniversary mode. Additional moments can be checked for research; installing them is unavailable.")
        note.setWordWrap(True)
        layout.addWidget(note)
        row = QtWidgets.QHBoxLayout()
        self.moments = QtWidgets.QComboBox()
        self.sides = QtWidgets.QComboBox()
        self.sides.addItems(["Away", "Home"])
        row.addWidget(self.moments, 1)
        row.addWidget(self.sides)
        layout.addLayout(row)
        self.binding_label = QtWidgets.QLabel("Load the project image to view Anniversary rosters.")
        self.binding_label.setWordWrap(True)
        layout.addWidget(self.binding_label)
        self.shared = QtWidgets.QCheckBox("I understand that every use of this historic roster will change")
        layout.addWidget(self.shared)
        self.table = QtWidgets.QTableWidget()
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        layout.addWidget(self.table, 1)
        buttons = QtWidgets.QHBoxLayout()
        for label, callback in (("Import roster CSV", self._import_dialog),
                                ("Export roster CSV", self._export_dialog),
                                ("Load scenario JSON", self._json_dialog),
                                ("Save build edits", self._save_dialog)):
            button = QtWidgets.QPushButton(label)
            button.clicked.connect(callback)
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.scenario_json = QtWidgets.QPlainTextEdit()
        self.scenario_json.setPlaceholderText('Scenario edits: {"schema":"' + espn.SCHEMA + '","moments":[]}')
        self.scenario_json.setMaximumHeight(120)
        layout.addWidget(self.scenario_json)
        self.message = QtWidgets.QLabel("")
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        self.moments.currentIndexChanged.connect(self._select)
        self.sides.currentIndexChanged.connect(self._select)
        self.shared.toggled.connect(self._editing)
        self.table.itemChanged.connect(self._changed)

    def set_source(self, source):
        self.set_catalog(espn.Catalog.load(source))

    def set_catalog(self, catalog):
        self.loading = True
        self.catalog, self.pending, self.current = catalog, {}, None
        self.moments.clear()
        for index in range(25):
            self.moments.addItem(f"{index + 1}. {catalog.moment(index)['text']['title']}")
        self.scenario_json.clear()
        self.loading = False
        self._select()

    def _editing(self, checked):
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.DoubleClicked | QtWidgets.QAbstractItemView.EditKeyPressed
                                   if checked and self.catalog else QtWidgets.QAbstractItemView.NoEditTriggers)

    def _select(self, *_):
        if self.loading or self.catalog is None:
            return
        moment, side = self.moments.currentIndex(), self.sides.currentText().lower()
        if moment < 0:
            return
        binding = self.catalog.binding(moment, side)
        index = binding["outer"]
        self.current = (moment, side, index)
        shared = ", ".join(f"{item['moment'] + 1} {item['side']}" for item in self.catalog.shared_uses(index))
        self.binding_label.setText(f"{binding['year']} {binding['selector'].title()}. Shared by moments: {shared}. "
                                   "The roster has 53 players. Names must fit the available name space.")
        self.loading = True
        self.shared.setChecked(index in self.pending)
        value = self.pending[index]["csv"] if index in self.pending else self.catalog.export_csv(moment, side)
        self._fill(value)
        self.loading = False
        self._editing(self.shared.isChecked())

    def _fill(self, value):
        rows = list(csv.reader(io.StringIO(value)))
        self.table.setColumnCount(len(rows[0]))
        self.table.setHorizontalHeaderLabels([name.replace("_", " ").title() for name in rows[0]])
        self.table.setRowCount(len(rows) - 1)
        for row_index, row in enumerate(rows[1:]):
            for column, value in enumerate(row):
                item = QtWidgets.QTableWidgetItem(value)
                if column < 2:
                    item.setFlags(item.flags() & ~QtCore.Qt.ItemIsEditable)
                self.table.setItem(row_index, column, item)

    def csv_text(self):
        stream = io.StringIO()
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(espn.CSV_COLUMNS)
        for row in range(self.table.rowCount()):
            writer.writerow([self.table.item(row, col).text() for col in range(self.table.columnCount())])
        return stream.getvalue()

    def _changed(self, *_):
        if self.loading or self.current is None:
            return
        if not self.shared.isChecked():
            self.message.setText("Acknowledge the shared roster before editing.")
            self._select()
            return
        moment, side, index = self.current
        self.pending[index] = {"moment": moment, "side": side, "shared_resource": True, "csv": self.csv_text()}
        self.message.setText("Edits are in memory. Save build edits to validate and stage them.")

    def import_csv_text(self, value):
        espn.require(self.catalog is not None and self.current is not None, "load a project image first")
        espn.require(self.shared.isChecked(), "acknowledge the shared roster before importing")
        moment, side, index = self.current
        # Validate a sparse import, then show all 53 rows from the resulting codec document.
        base = self.catalog
        if index in self.pending:
            previous, _ = base.import_csv(moment, side, self.pending[index]["csv"])
            base = espn.Catalog({**base.resources, index: (base.resources[index][0], previous)}, base.manifest)
        raw, _ = base.import_csv(moment, side, value)
        document = self.catalog.validate_roster(index, raw)
        rows = csv.DictReader(io.StringIO(espn.rr.export_csv(document)))
        stream = io.StringIO()
        writer = csv.DictWriter(stream, espn.CSV_COLUMNS, extrasaction="ignore", lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)
        self.loading = True
        self._fill(stream.getvalue())
        self.loading = False
        self._changed()

    def make_plan(self):
        espn.require(self.catalog is not None, "load a project image first")
        text = self.scenario_json.toPlainText().strip()
        # Share the bounded, duplicate-key-rejecting reader with the command line.
        if text:
            import tempfile
            with tempfile.TemporaryDirectory(prefix="espn25-authoring-") as temporary:
                path = Path(temporary).resolve() / "edits.json"
                espn.require(len(text.encode("utf-8")) <= espn.MAX_JSON, "JSON exceeds 2 MiB")
                path.write_text(text, encoding="utf-8", newline="\n")
                edits = espn.read_json(path)
        else:
            edits = {"schema": espn.SCHEMA}
        if edits.get("schema") == espn.DRAFT_SCHEMA:
            table = self.catalog.research_table(edits)
            raise espn.Espn25Error(f"Research table validates with {espn.u32(table, 8)} moments. "
                                   "Installation awaits menu paging and saved completion checks.")
        espn.keys(edits, ("schema", "moments"), ("schema",))
        plan = self.catalog.prepare({**edits, "rosters": list(self.pending.values())})
        espn.require({row["outer"] for row in plan["rosters"]} == set(self.pending),
                     "A team selection changed under a roster edit. Save team edits first, then reload the project.")
        return plan

    def save_plan(self, path):
        plan = self.make_plan()
        espn.write_json(path, plan)
        self.plan_ready.emit({"path": str(Path(path).resolve()), "plan": plan})
        self.message.setText("Build edits saved and validated. Use a new output image to apply them.")
        return plan

    def _guard(self, operation):
        try:
            operation()
        except (ValueError, OSError, csv.Error) as exc:
            self.message.setText(str(exc))

    def _import_dialog(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Import Anniversary roster", "", "CSV (*.csv)")
        if path:
            def load():
                with Path(path).open("rb") as stream:
                    raw = stream.read(256 * 1024 + 1)
                espn.require(len(raw) <= 256 * 1024, "CSV exceeds 256 KiB")
                self.import_csv_text(raw.decode("utf-8-sig"))
            self._guard(load)

    def _export_dialog(self):
        if self.current is None:
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Export Anniversary roster", "", "CSV (*.csv)")
        if path:
            self._guard(lambda: Path(path).write_text(self.csv_text(), encoding="utf-8", newline="\n"))

    def _json_dialog(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Load scenario edits", "", "JSON (*.json)")
        if path:
            self._guard(lambda: self.scenario_json.setPlainText(json.dumps(espn.read_json(path), indent=2)))

    def _save_dialog(self):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save Anniversary build edits", "", "JSON (*.json)")
        if path:
            self._guard(lambda: self.save_plan(path))
