"""Opt-in, shared-node Coverage Geometry workspace."""
from __future__ import annotations

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (
    QAbstractItemView, QFormLayout, QHBoxLayout, QLabel, QPlainTextEdit,
    QPushButton, QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from mod_editor.core import apf2k8_coverage_tuning as coverage


class CoverageGeometryPanel(QWidget):
    modifiedChanged = pyqtSignal()

    def __init__(self, facade, run_task):
        super().__init__()
        self.facade, self.run_task = facade, run_task
        self._generation = 0
        self._snapshot = None
        self._rows = ()
        self._defaults = {}
        self._edits = {}
        self._busy = False
        layout = QVBoxLayout(self)
        title = QLabel("Coverage Geometry (experimental)")
        title.setObjectName("panelTitle")
        layout.addWidget(title)
        note = QLabel("Gameplay UNWITNESSED. These landmarks and extents belong to shared zone nodes. "
                      "Every play, slot and chain step using the selected node is listed below. "
                      "Source values are retained until you explicitly stage a change.")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Node", "Landmark X (ft)", "Drop depth (ft)",
                                             "Lateral extent (yd)", "Depth extent (yd)", "Uses"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        layout.addWidget(self.table, 1)
        form = QFormLayout()
        self.knobs = {}
        for name, bounds in coverage.KNOB_RANGES.items():
            spin = QSpinBox()
            spin.setRange(*bounds)
            self.knobs[name] = spin
            form.addRow(name.replace("_", " ").title(), spin)
        layout.addLayout(form)
        self.uses = QPlainTextEdit()
        self.uses.setReadOnly(True)
        self.uses.setMaximumHeight(100)
        layout.addWidget(self.uses)
        buttons = QHBoxLayout()
        self.apply_button = QPushButton("Apply selected node")
        self.revert_button = QPushButton("Revert selected node")
        self.revert_all_button = QPushButton("Revert coverage profile")
        for button in (self.apply_button, self.revert_button, self.revert_all_button):
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.status = QLabel("Load your APF game to inspect its zone nodes.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.table.currentCellChanged.connect(self._select)
        self.apply_button.clicked.connect(self._apply)
        self.revert_button.clicked.connect(self._revert)
        self.revert_all_button.clicked.connect(lambda: self._stage(()))
        self.set_busy(False)

    def _key(self):
        session = self.facade.session
        return (id(session), tuple((m.asset_id, m.replacement_sha256)
                                  for m in session.modifications)) if session else None

    def set_context(self):
        key = self._key()
        if key == self._snapshot:
            self.set_busy(self._busy)
            return
        self._snapshot = key
        self._generation += 1
        generation = self._generation
        self._rows = ()
        self.table.setRowCount(0)
        self.uses.clear()
        self.set_busy(self._busy)
        if key is None:
            self._edits = {}
            self.status.setText("Load your APF game to inspect its zone nodes.")
            return
        self.status.setText("Reading source values and all composed assignment uses…")

        def complete(result):
            if generation != self._generation:
                return
            if key != self._key():
                self.set_context()
                return
            defaults, rows, edits, _report = result
            self._defaults = {row["node_index"]: row for row in defaults}
            self._rows = rows
            self._edits = {e.node_index: e for e in edits}
            self.table.setRowCount(len(rows))
            for row_index, row in enumerate(rows):
                values = [row["node_index"], *(row[k] for k in coverage.KNOB_RANGES), len(row["uses"])]
                for column, value in enumerate(values):
                    self.table.setItem(row_index, column, QTableWidgetItem(str(value)))
            self.table.selectRow(0)
            self.status.setText(f"{len(rows)} shared zone nodes; {len(edits)} staged. Gameplay UNWITNESSED.")
            self.set_busy(False)

        self.run_task("Reading Coverage Geometry", self.facade.coverage_context, complete, False)

    refresh = set_context

    def set_busy(self, busy):
        self._busy = busy
        enabled = bool(self._rows) and not busy
        for control in (*self.knobs.values(), self.apply_button, self.revert_button, self.revert_all_button):
            control.setEnabled(enabled)

    def _select(self, *_args):
        index = self.table.currentRow()
        if not 0 <= index < len(self._rows):
            return
        row = self._rows[index]
        for name, spin in self.knobs.items():
            spin.setValue(row[name])
        self.uses.setPlainText("\n".join(
            f"Play {use['play_index']} · slot {use['slot_index']} · chain step {use['chain_step']}"
            for use in row["uses"]) or "No current assignment uses this node.")

    def _apply(self):
        node = self._rows[self.table.currentRow()]["node_index"]
        values = {k: spin.value() for k, spin in self.knobs.items()
                  if spin.value() != self._defaults[node][k]}
        edits = dict(self._edits)
        if values:
            edits[node] = coverage.ZoneEdit(node, **values)
        else:
            edits.pop(node, None)
        self._stage(tuple(edits[k] for k in sorted(edits)))

    def _revert(self):
        node = self._rows[self.table.currentRow()]["node_index"]
        self._stage(tuple(e for k, e in sorted(self._edits.items()) if k != node))

    def _stage(self, edits):
        key = self._key()
        def operation(progress):
            with self.facade._session_lock:
                if key != self._key():
                    raise ValueError("Coverage source or project changed; reload its current values.")
                return self.facade.apply_coverage_geometry(edits, progress)
        def complete(_result):
            self.modifiedChanged.emit()
            self.set_context()
        self.run_task("Staging Coverage Geometry", operation, complete, True)
