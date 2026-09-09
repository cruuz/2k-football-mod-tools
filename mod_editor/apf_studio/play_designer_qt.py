"""APF-owned play/formation designer. Its protected page wiring is in WIRING.md."""
from __future__ import annotations

import copy

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QMessageBox, QPushButton, QSpinBox, QTableWidget,
    QVBoxLayout, QWidget,
)

from mod_editor.core import apf2k8_play_codec as codec
from mod_editor.core.apf2k8_play_designer import compile_design, empty_plan, STATUS
from mod_editor.core.apf2k8_play_concepts import RECIPES, NOTICE, concept_request


def spin(lo, hi, value):
    widget = QSpinBox()
    widget.setRange(lo, hi)
    widget.setValue(value)
    return widget


class _RecordDialog(QDialog):
    def __init__(self, book, kind, next_index, parent=None):
        super().__init__(parent)
        self.book, self.kind, self.next_index = book, kind, next_index
        self.root = QVBoxLayout(self)
        form = QFormLayout()
        self.mode, self.donor, self.target = QComboBox(), QComboBox(), QComboBox()
        for title, value in (("Append new", "append"), ("Edit existing", "edit"), ("Replace chosen slot", "replace")):
            self.mode.addItem(title, value)
        records = book.plays if kind == "plays" else book.formations
        name = book.play_name if kind == "plays" else book.formation_name
        for i in range(len(records)):
            self.donor.addItem(f"{i}: {name(i)}", i)
            self.target.addItem(f"{i}: {name(i)}", i)
        self.name = QLineEdit("My play" if kind == "plays" else "My formation")
        form.addRow("Action", self.mode)
        form.addRow("Source", self.donor)
        form.addRow("Replacement slot", self.target)
        form.addRow("Name", self.name)
        self.root.addLayout(form)
        self.notice = QLabel()
        self.notice.setWordWrap(True)
        self.root.addWidget(self.notice)
        self.mode.currentIndexChanged.connect(self._mode_changed)
        self._mode_changed()

    def _mode_changed(self):
        self.target.setEnabled(self.mode.currentData() == "replace")
        self.notice.setText(f"Appends at index {self.next_index}. Replacement changes every book call using the chosen slot. Existing edits keep their index.")

    def common(self):
        mode = self.mode.currentData()
        donor = self.donor.currentData()
        return {"mode": mode, "target": self.next_index if mode == "append" else donor if mode == "edit" else self.target.currentData(),
                "donor": donor, "name": self.name.text() or None}

    def buttons(self):
        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        self.root.addWidget(box)


class PlayDesignDialog(_RecordDialog):
    def __init__(self, book, next_index, parent=None):
        super().__init__(book, "plays", next_index, parent)
        self.setWindowTitle("Design Play")
        self.resize(650, 580)
        self.nodes, self.copies = {}, {}
        form = QFormLayout()
        self.slot, self.node, self.field, self.route = QComboBox(), QComboBox(), QComboBox(), QComboBox()
        for s in range(11):
            self.slot.addItem(f"Player slot {s}", s)
        self.route.addItem("Keep source assignment", None)
        for i in range(len(book.plays)):
            self.route.addItem(f"{i}: {book.play_name(i)}", i)
        self.value = spin(-32768, 32767, 0)
        for label, widget in (("Player", self.slot), ("Copy same player's assignment from", self.route),
                              ("Assignment node", self.node), ("Field", self.field), ("Value (integer feet / selector)", self.value)):
            form.addRow(label, widget)
        self.root.addLayout(form)
        add = QPushButton("Apply field to draft")
        add.clicked.connect(self._add)
        self.root.addWidget(add)
        self.summary = QListWidget()
        self.root.addWidget(self.summary)
        label = QLabel("QB depth: edit movement Y before Pass. First read selects an eligible receiver; it does not set drop steps. Shared assignments are isolated when needed.")
        label.setWordWrap(True)
        self.root.addWidget(label)
        self.slot.currentIndexChanged.connect(self._slot_changed)
        self.donor.currentIndexChanged.connect(self._donor_changed)
        self.route.currentIndexChanged.connect(self._route_changed)
        self.node.currentIndexChanged.connect(self._fields)
        self._slot_changed()
        self.buttons()

    def _donor_changed(self):
        self.nodes.clear()
        self.copies.clear()
        self.summary.clear()
        self._slot_changed()

    def _slot_changed(self):
        self.route.blockSignals(True)
        self.route.setCurrentIndex(self.route.findData(self.copies.get(self.slot.currentData())))
        self.route.blockSignals(False)
        self._load_nodes()

    def _route_changed(self):
        slot = self.slot.currentData()
        value = self.route.currentData()
        self.nodes = {k: v for k, v in self.nodes.items() if k[0] != slot}
        if value is None:
            self.copies.pop(slot, None)
        else:
            self.copies[slot] = value
        self._load_nodes()
        self._summary()

    def _load_nodes(self):
        self.node.clear()
        donor = self.copies.get(self.slot.currentData(), self.donor.currentData())
        self.chain = self.book.chain(donor, self.slot.currentData())
        for i, node in enumerate(self.chain):
            self.node.addItem(f"{i}: {node.name}", i)
        self._fields()

    def _fields(self):
        self.field.clear()
        index = self.node.currentData()
        if index is None or not hasattr(self, "chain"):
            return
        op = self.chain[index].op
        fields = {4: ("x_ft", "y_ft"), 18: ("distance_ft", "segment_type"), 13: ("x_ft", "y_ft"),
                  14: ("cushion_ft",), 6: ("first_read",), 11: ("lane",), 12: ("lane",),
                  28: ("mode", "first_flag", "first_lane", "second_flag", "second_lane", "selector")}.get(op, ())
        for field in fields:
            self.field.addItem(field.replace("_", " "), field)

    def _add(self):
        if self.field.currentData() is None:
            return
        try:
            self.chain[self.node.currentData()].with_field(self.field.currentData(), self.value.value())
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid assignment field", str(exc))
            return
        self.nodes[self.slot.currentData(), self.node.currentData(), self.field.currentData()] = self.value.value()
        self._summary()

    def _summary(self):
        self.summary.clear()
        for slot, donor in sorted(self.copies.items()):
            self.summary.addItem(f"Slot {slot}: copy assignment from {self.book.play_name(donor)}")
        for (slot, node, field), value in sorted(self.nodes.items()):
            self.summary.addItem(f"Slot {slot}, node {node}: {field} = {value}")

    def request(self):
        return {**self.common(), "copies": [[slot, donor] for slot, donor in sorted(self.copies.items())],
                "nodes": [[*key, value] for key, value in sorted(self.nodes.items())]}


class FormationDesignDialog(_RecordDialog):
    def __init__(self, book, next_index, parent=None):
        super().__init__(book, "formations", next_index, parent)
        self.setWindowTitle("Design Formation")
        self.resize(760, 640)
        label = QLabel("Alignment in centimetres: X across the field, Y downfield. Each player has three alignment variants. Personnel and slot order come from the source formation.")
        label.setWordWrap(True)
        self.root.addWidget(label)
        self.table = QTableWidget(11, 6)
        self.table.setHorizontalHeaderLabels([f"{axis} · variant {v}" for v in range(3) for axis in ("X", "Y")])
        self.table.setVerticalHeaderLabels([f"Slot {s}" for s in range(11)])
        self.root.addWidget(self.table)
        self.donor.currentIndexChanged.connect(self._populate)
        self._populate()
        self.buttons()

    def _populate(self):
        for s, slot in enumerate(self.book.formations[self.donor.currentData()].slots):
            for variant in range(3):
                self.table.setCellWidget(s, variant * 2, spin(-32768, 32767, slot.x[variant]))
                self.table.setCellWidget(s, variant * 2 + 1, spin(-32768, 32767, slot.y[variant]))

    def request(self):
        positions = []
        original = self.book.formations[self.donor.currentData()]
        for s in range(11):
            for v in range(3):
                x, y = (self.table.cellWidget(s, v * 2 + k).value() for k in range(2))
                if (x, y) != (original.slots[s].x[v], original.slots[s].y[v]):
                    positions.append([s, v, x, y])
        return {**self.common(), "positions": positions}


class CpuCallDialog(QDialog):
    def __init__(self, book, cpu_books, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add a CPU book call")
        self.cpu_books = cpu_books
        root = QFormLayout(self)
        self.outer, self.record, self.play, self.formation, self.donor = [QComboBox() for _ in range(5)]
        for i, cpu in cpu_books.items():
            self.outer.addItem(cpu.name, i)
        for i in range(len(book.plays)):
            self.play.addItem(f"{i}: {book.play_name(i)}", i)
        self.play.setCurrentIndex(len(book.plays) - 1)
        for i in range(len(book.formations)):
            self.formation.addItem(f"{i}: {book.formation_name(i)}", i)
        for title, widget in (("CPU book", self.outer), ("Record", self.record), ("Play", self.play), ("Formation", self.formation), ("For an empty record, inherit from", self.donor)):
            root.addRow(title, widget)
        self.outer.currentIndexChanged.connect(self._records)
        self.record.currentIndexChanged.connect(self._formation)
        self._records()
        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        root.addRow(box)

    def _records(self):
        self.record.clear()
        self.donor.clear()
        self.donor.addItem("Existing record: keep its formation", None)
        for row in self.cpu_books[self.outer.currentData()].records:
            self.record.addItem(f"{row.record_index}: formation {row.formation_index}, {len(row.entries)} plays" if row.entries else f"{row.record_index}: empty", row.record_index)
            if row.entries:
                self.donor.addItem(f"{row.record_index}: formation {row.formation_index}", row.record_index)

    def _formation(self):
        ri = self.record.currentData()
        if ri is not None:
            row = self.cpu_books[self.outer.currentData()].records[ri]
            if row.entries:
                self.formation.setCurrentIndex(self.formation.findData(row.formation_index))
                self.donor.setCurrentIndex(0)

    def request(self):
        return {key: widget.currentData() for key, widget in (("outer", self.outer), ("record", self.record), ("play", self.play), ("formation", self.formation), ("donor_record", self.donor))}


class PlayDesignerPanel(QWidget):
    modifiedChanged = pyqtSignal()

    def __init__(self, facade, run_task):
        super().__init__()
        self.facade, self.run_task = facade, run_task
        self.source = self.book = self.draft = None
        self.dirty = False
        self.cpu_books = {}
        root = QVBoxLayout(self)
        title = QLabel("Design APF plays and formations")
        title.setObjectName("panelTitle")
        root.addWidget(title)
        status = QLabel(STATUS)
        status.setWordWrap(True)
        root.addWidget(status)
        buttons = QHBoxLayout()
        self.play_button, self.formation_button, self.cpu_button = [QPushButton(t) for t in ("Design Play…", "Design Formation…", "Add CPU call…")]
        for button in (self.play_button, self.formation_button, self.cpu_button):
            buttons.addWidget(button)
        self.play_button.clicked.connect(lambda: self._record("plays"))
        self.formation_button.clicked.connect(lambda: self._record("formations"))
        self.cpu_button.clicked.connect(self._cpu)
        root.addLayout(buttons)
        recipe = QHBoxLayout()
        self.concept = QComboBox()
        self.concept.addItems(RECIPES)
        self.concept_button = QPushButton("Add concept recipe")
        self.concept_button.clicked.connect(self._concept)
        recipe.addWidget(self.concept)
        recipe.addWidget(self.concept_button)
        root.addLayout(recipe)
        note = QLabel(NOTICE)
        note.setWordWrap(True)
        root.addWidget(note)
        self.summary = QListWidget()
        root.addWidget(self.summary)
        self.stage_button = QPushButton("Verify allocations and stage design")
        self.stage_button.clicked.connect(self._stage)
        root.addWidget(self.stage_button)
        self.reload_button = QPushButton("Reload staged design")
        self.reload_button.clicked.connect(self.set_context)
        root.addWidget(self.reload_button)
        self.status = QLabel("Load a game to design plays.")
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        self._enabled(False)

    def _enabled(self, value):
        for button in (self.play_button, self.formation_button, self.cpu_button, self.stage_button, self.concept_button):
            button.setEnabled(value)
        self.stage_button.setEnabled(bool(value and self.draft and any(self.draft[k] for k in ("plays", "formations", "cpu_calls"))))

    def set_context(self):
        self._enabled(False)
        if not self.facade.source_ready:
            self.source = self.book = self.draft = None
            self.summary.clear()
            return
        self.run_task("Loading APF designer", lambda progress: self.facade.play_design_context(progress=progress), self.set_data, False)

    def set_data(self, data):
        self.source, staged, self.cpu_books = data
        self.book = codec.Book.from_bytes(self.source)
        self.draft = copy.deepcopy(staged) if staged else empty_plan(self.source)
        self.dirty = False
        self._summary()
        self._enabled(True)

    def _next(self, kind):
        count = len(self.book.plays) if kind == "plays" else len(self.book.formations)
        return count + sum(r["mode"] == "append" for r in self.draft[kind])

    def _accept(self, draft):
        try:
            compile_design(self.source, draft)
        except ValueError as exc:
            QMessageBox.warning(self, "Cannot apply design", str(exc))
            return False
        self.draft = draft
        self.dirty = True
        self._summary()
        self._enabled(True)
        return True

    def _record(self, kind):
        dialog = (PlayDesignDialog if kind == "plays" else FormationDesignDialog)(self.book, self._next(kind), self)
        if dialog.exec_() == QDialog.Accepted:
            request = dialog.request()
            draft = copy.deepcopy(self.draft)
            draft[kind] = [r for r in draft[kind] if r["target"] != request["target"]] + [request]
            self._accept(draft)

    def _concept(self):
        try:
            request = concept_request(self.source, self.concept.currentText(), self._next("plays"))
            draft = copy.deepcopy(self.draft)
            draft["plays"].append(request)
            self._accept(draft)
        except ValueError as exc:
            QMessageBox.warning(self, "Cannot add concept", str(exc))

    def _cpu(self):
        body = compile_design(self.source, self.draft).replacement if any(self.draft[k] for k in ("plays", "formations", "cpu_calls")) else self.source
        dialog = CpuCallDialog(codec.Book.from_bytes(body), self.cpu_books, self)
        if dialog.exec_() == QDialog.Accepted:
            draft = copy.deepcopy(self.draft)
            draft["cpu_calls"].append(dialog.request())
            self._accept(draft)

    def _summary(self):
        self.summary.clear()
        for kind in ("plays", "formations"):
            for r in self.draft[kind]:
                self.summary.addItem(f"{r['mode'].title()} {kind[:-1]} {r['target']}: {r['name'] or 'keep name'}")
        for r in self.draft["cpu_calls"]:
            self.summary.addItem(f"CPU {r['outer']}, record {r['record']}: play {r['play']}, formation {r['formation']}")
        self.status.setText("Draft ready. Add a CPU call for each new play you want the CPU book to offer. Verify and stage before saving the project.")

    def _stage(self):
        draft = copy.deepcopy(self.draft)
        self.run_task("Verifying APF design", lambda progress: self.facade.apply_play_design(draft, progress=progress), self._staged, True)

    def _staged(self, report):
        self.dirty = False
        budgets = ", ".join(f"outer {r['outer']}: {r['free_bytes']} bytes free" for r in report["resources"])
        self.status.setText("Staged and reparsed. " + budgets + ". In-game result UNWITNESSED.")
        self.modifiedChanged.emit()

    def refresh(self):
        if not self.dirty or not self.facade.source_ready:
            self.set_context()
