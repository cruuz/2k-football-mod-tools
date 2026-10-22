"""APF-owned play/formation designer. Its protected page wiring is in WIRING.md."""
from __future__ import annotations

from mod_editor.gui.ux_text import failure_body

import copy
import struct

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QSpinBox, QTableWidget,
    QVBoxLayout, QWidget,
)

from mod_editor.core import apf2k8_play_codec as codec
from mod_editor.core.errors import ValidationError
from mod_editor.core.apf2k8_play_designer import (
    FAMILY_ORDER, assign_plays, compile_design, empty_plan, formation_family, formation_personnel, formation_side, offered_plays,
    play_side, unlockable_formations, OFFER_LIMIT, OFFER_ROW, STATUS,
)
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
        self.resize(650, 780)
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
        mirror_one = QPushButton("Mirror this player's assignment")
        mirror_one.setToolTip("Flip left/right the way the game does for a flipped formation: X offsets, block turns, "
                              "handoff hole (h becomes 9-h), pass-block side and rush lanes. Press again to undo.")
        mirror_one.clicked.connect(lambda: self._mirror(False))
        mirror_pair = QPushButton("Mirror this player and the player they hand off to (QB + HB)")
        mirror_pair.setToolTip("Mirrors this player's assignment and the assignment of every player this one fakes a "
                               "handoff to or hands off to, so the fake stays lined up.")
        mirror_pair.clicked.connect(lambda: self._mirror(True))
        self.root.addWidget(mirror_one)
        self.root.addWidget(mirror_pair)
        self.summary = QListWidget()
        self.root.addWidget(self.summary)
        label = QLabel("QB depth: edit movement Y before Pass. First read selects an eligible receiver; it does not set drop steps. Shared assignments are isolated when needed.")
        label.setWordWrap(True)
        self.root.addWidget(label)
        offer_label = QLabel("Playbook Manager: formations that offer this play (checked). A new play starts with the "
                             "formations of its Source play. Edit/Replace keep the current formations unless you change them.")
        offer_label.setWordWrap(True)
        self.root.addWidget(offer_label)
        self.offer_list = QListWidget()
        self.offer_list.setMaximumHeight(160)
        for i in range(len(book.formations)):
            item = QListWidgetItem(f"{i}: {book.formation_name(i)}")
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            self.offer_list.addItem(item)
        self.root.addWidget(self.offer_list)
        self._offer_default = set()
        self.slot.currentIndexChanged.connect(self._slot_changed)
        self.donor.currentIndexChanged.connect(self._donor_changed)
        self.route.currentIndexChanged.connect(self._route_changed)
        self.node.currentIndexChanged.connect(self._fields)
        for combo in (self.mode, self.donor, self.target):
            combo.currentIndexChanged.connect(self._reset_offer)
        self._slot_changed()
        self._reset_offer()
        self.buttons()

    def _offered(self, play):
        relation = self.book.opaque_relation
        found = set()
        for f in range(len(self.book.formations)):
            word = struct.unpack_from(">I", relation, f * OFFER_ROW + (play // 32) * 4)[0]
            if word >> (play % 32) & 1:
                found.add(f)
        return found

    def _reset_offer(self, *_):
        mode = self.mode.currentData()
        reference = self.target.currentData() if mode == "replace" else self.donor.currentData()
        self._offer_default = self._offered(reference) if reference is not None else set()
        for i in range(self.offer_list.count()):
            self.offer_list.item(i).setCheckState(Qt.Checked if i in self._offer_default else Qt.Unchecked)

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
                  28: ("mode", "first_flag", "first_lane", "second_flag", "second_lane", "selector"),
                  1: ("x_ft",), 9: ("x_ft",), 21: ("x_ft",), 24: ("x_ft",), 17: ("turn", "x_ft"),
                  19: ("k",), 20: ("k",), 22: ("a", "hole"), 23: ("a", "hole")}.get(op, ())
        for field in fields:
            self.field.addItem(field.replace("_", " "), field)

    def _add(self):
        if self.field.currentData() is None:
            return
        try:
            self.chain[self.node.currentData()].with_field(self.field.currentData(), self.value.value())
        except (ValueError, ValidationError) as exc:
            QMessageBox.warning(self, "Invalid assignment field", failure_body(exc))
            return
        self.nodes[self.slot.currentData(), self.node.currentData(), self.field.currentData()] = self.value.value()
        self._summary()

    def _effective_chain(self, slot):
        """The slot's chain as it will be compiled: source (or copied) assignment plus staged field edits."""
        donor = self.copies.get(slot, self.donor.currentData())
        chain = list(self.book.chain(donor, slot))
        for (s, node, field), value in sorted(self.nodes.items()):
            if s == slot and node < len(chain):
                chain[node] = chain[node].with_field(field, value)
        return chain

    def _mirror(self, with_partners):
        slots = [self.slot.currentData()]
        if with_partners:
            # Fake Handoff To / Handoff To (0x14 / 0x13) name the player who takes the ball.
            for node in self._effective_chain(slots[0]):
                if node.op in (0x13, 0x14) and node.operands[0] not in slots:
                    slots.append(node.operands[0])
        notes = []
        staged = 0
        for slot in slots:
            chain = self._effective_chain(slot)
            edits, skipped = codec.mirror_chain_edits(chain)
            for node, field, value in edits:
                self.nodes[slot, node, field] = value
                staged += 1
            notes.extend(f"Slot {slot}: {text}" for text in skipped)
        self._load_nodes()
        self._summary()
        text = f"Mirrored player slot(s) {', '.join(str(s) for s in slots)}: {staged} field edit(s) staged in the draft."
        if not staged:
            text += " Nothing in these assignments has a left/right side to flip."
        if notes:
            text += "\n\nNot mirrored:\n" + "\n".join(notes[:12])
        QMessageBox.information(self, "Mirror assignment", text)

    def _summary(self):
        self.summary.clear()
        for slot, donor in sorted(self.copies.items()):
            self.summary.addItem(f"Slot {slot}: copy assignment from {self.book.play_name(donor)}")
        for (slot, node, field), value in sorted(self.nodes.items()):
            self.summary.addItem(f"Slot {slot}, node {node}: {field} = {value}")

    def request(self):
        common = self.common()
        checked = {i for i in range(self.offer_list.count()) if self.offer_list.item(i).checkState() == Qt.Checked}
        # Append always states its formations; Edit/Replace say nothing (null) unless the list was changed.
        offer = sorted(checked) if common["mode"] == "append" or checked != self._offer_default else None
        return {**common, "copies": [[slot, donor] for slot, donor in sorted(self.copies.items())],
                "nodes": [[*key, value] for key, value in sorted(self.nodes.items())], "offer": offer}


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


class FormationOfferDialog(QDialog):
    """Choose which plays one formation offers in the in-game Playbook Manager (at most OFFER_LIMIT)."""

    def __init__(self, book, source, current, locked, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Playbook Manager plays per formation")
        self.resize(560, 760)
        self.book, self.source, self.current, self.locked = book, source, current, locked
        self.sets, self.baseline, self.notes = {}, {}, []
        self.shown = None
        root = QVBoxLayout(self)
        info = QLabel(
            f"The Playbook Manager lists at most {OFFER_LIMIT} plays per formation, checked and unchecked together, and cuts the rest "
            "off. Tick the plays this formation should offer. Plays in your default playbook for it can't be removed. If your saved "
            "playbook (in the game) has a play checked that you remove here, uncheck it in the game first or the manager may crash.")
        info.setWordWrap(True)
        root.addWidget(info)
        self.formation = QComboBox()
        for f in range(len(book.formations)):
            side = formation_side(current, f)
            if side in (0, 1):
                self.formation.addItem(f"{f}: {book.formation_name(f)} ({'offense' if side == 0 else 'defense'})", f)
        root.addWidget(self.formation)
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Filter plays by name or number")
        root.addWidget(self.filter)
        self.list = QListWidget()
        root.addWidget(self.list)
        self.count = QLabel()
        root.addWidget(self.count)
        self.spread = QComboBox()
        self.spread.addItem("Only this formation", None)
        self.spread.addItem("Also add my new picks to every other formation on this side (as many as fit)", "side")
        root.addWidget(self.spread)
        row = QHBoxLayout()
        self.reset_button = QPushButton("Reset this formation to retail")
        row.addWidget(self.reset_button)
        root.addLayout(row)
        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        root.addWidget(box)
        self.formation.currentIndexChanged.connect(self._switch)
        self.filter.textChanged.connect(self._filter)
        self.list.itemChanged.connect(self._changed)
        self.reset_button.clicked.connect(self._reset)
        self._switch()

    def _retail(self, f):
        return set(offered_plays(self.source, f)) if f < struct.unpack_from(">I", self.source, 0x34)[0] else set()

    def _effective(self, f):
        return set(self.sets[f]) if f in self.sets else set(offered_plays(self.current, f))

    def _store(self):
        if self.shown is not None:
            self.sets[self.shown] = {self.list.item(i).data(Qt.UserRole) for i in range(self.list.count())
                                     if self.list.item(i).checkState() == Qt.Checked}

    def _switch(self, *_):
        self._store()
        f = self.formation.currentData()
        self.shown = f
        if f is not None and f not in self.baseline:
            self.baseline[f] = set(offered_plays(self.current, f))
        self._fill(self._effective(f) | self.locked.get(f, set()))

    def _fill(self, chosen):
        f = self.shown
        side = formation_side(self.current, f)
        retail = self._retail(f)
        locked = self.locked.get(f, set())
        self.list.blockSignals(True)
        self.list.clear()
        for p in range(len(self.book.plays)):
            if play_side(self.current, p) != side and p not in retail:
                continue
            tag = " (default playbook)" if p in locked else " (retail)" if p in retail else ""
            item = QListWidgetItem(f"{p}: {self.book.play_name(p)}{tag}")
            item.setData(Qt.UserRole, p)
            item.setFlags(Qt.ItemIsUserCheckable if p in locked else Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            item.setCheckState(Qt.Checked if p in chosen or p in locked else Qt.Unchecked)
            self.list.addItem(item)
        self.list.blockSignals(False)
        self._filter()
        self._recount()

    def _checked(self):
        return sum(self.list.item(i).checkState() == Qt.Checked for i in range(self.list.count()))

    def _recount(self, message=""):
        self.count.setText(f"Offered: {self._checked()} / {OFFER_LIMIT}  (retail offers {len(self._retail(self.shown))})  {message}")

    def _changed(self, item):
        if self._checked() > OFFER_LIMIT:
            self.list.blockSignals(True)
            item.setCheckState(Qt.Unchecked)
            self.list.blockSignals(False)
            self._recount(f"Limit reached: untick another play first.")
        else:
            self._recount()

    def _filter(self, *_):
        text = self.filter.text().strip().lower()
        for i in range(self.list.count()):
            self.list.item(i).setHidden(bool(text) and text not in self.list.item(i).text().lower())

    def _reset(self):
        f = self.shown
        self._fill(self._retail(f) | self.locked.get(f, set()))

    def request(self):
        self._store()
        f_shown = self.shown
        out = {f: sorted(plays) for f, plays in self.sets.items() if plays != self.baseline.get(f, plays)}
        if self.spread.currentData() == "side" and f_shown is not None:
            side = formation_side(self.current, f_shown)
            adds = self.sets[f_shown] - self._retail(f_shown)
            groups = unlockable_formations(self.source)
            for g in groups["offense" if side == 0 else "defense"]:
                if g == f_shown:
                    continue
                base = self._effective(g) | self.locked.get(g, set())
                missing = sorted(adds - base)
                take = missing[:max(0, OFFER_LIMIT - len(base))]
                if take:
                    out[g] = sorted(base | set(take))
                if len(take) < len(missing):
                    self.notes.append(f"{self.book.formation_name(g)}: {len(missing) - len(take)} of your picks did not fit")
        return [{"formation": f, "plays": plays} for f, plays in sorted(out.items())]


class AssignPlaysDialog(QDialog):
    """Pick plays, then choose the formations that should offer them: by personnel, by family, or by hand."""

    def __init__(self, book, source, current, locked, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Assign plays to formations")
        self.resize(760, 860)
        self.book, self.source, self.current, self.locked = book, source, current, locked
        self.source_book = codec.Book.from_bytes(source)
        self.notes = []
        self.keys, self.families, self.formation_ids = {}, {}, []
        root = QVBoxLayout(self)
        info = QLabel(
            f"Tick the plays, then choose where the Playbook Manager should offer them. A formation holds at most {OFFER_LIMIT} plays; "
            "plays that do not fit are skipped, lowest numbers first. Plays your default playbook uses can't be removed.")
        info.setWordWrap(True)
        root.addWidget(info)
        top = QHBoxLayout()
        self.side = QComboBox()
        self.side.addItem("Offense", 0)
        self.side.addItem("Defense", 1)
        self.operation = QComboBox()
        self.operation.addItem("Offer the ticked plays", "add")
        self.operation.addItem("Stop offering the ticked plays", "remove")
        top.addWidget(self.side)
        top.addWidget(self.operation)
        root.addLayout(top)
        self.play_filter = QLineEdit()
        self.play_filter.setPlaceholderText("Filter plays by name or number")
        root.addWidget(self.play_filter)
        self.plays = QListWidget()
        root.addWidget(self.plays)
        shortcuts = QHBoxLayout()
        self.personnel = QListWidget()
        self.family = QListWidget()
        shortcuts.addWidget(self.personnel)
        shortcuts.addWidget(self.family)
        root.addLayout(shortcuts)
        row = QHBoxLayout()
        self.match = QComboBox()
        self.match.addItem("Personnel AND family (narrower)", "and")
        self.match.addItem("Personnel OR family (wider)", "or")
        self.set_button = QPushButton("Set checklist to matches")
        self.add_button = QPushButton("Add matches to checklist")
        self.all_button = QPushButton("All")
        self.none_button = QPushButton("None")
        for widget in (self.match, self.set_button, self.add_button, self.all_button, self.none_button):
            row.addWidget(widget)
        root.addLayout(row)
        self.target_filter = QLineEdit()
        self.target_filter.setPlaceholderText("Filter formations by name")
        root.addWidget(self.target_filter)
        self.targets = QListWidget()
        root.addWidget(self.targets)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        root.addWidget(self.summary)
        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        root.addWidget(box)
        self.side.currentIndexChanged.connect(self._rebuild)
        self.operation.currentIndexChanged.connect(self._summarize)
        self.play_filter.textChanged.connect(lambda *_: self._filter(self.plays, self.play_filter))
        self.target_filter.textChanged.connect(lambda *_: self._filter(self.targets, self.target_filter))
        for widget in (self.plays, self.targets):
            widget.itemChanged.connect(self._summarize)
        self.set_button.clicked.connect(lambda: self._apply_matches(False))
        self.add_button.clicked.connect(lambda: self._apply_matches(True))
        self.all_button.clicked.connect(lambda: self._set_all(self.targets, True))
        self.none_button.clicked.connect(lambda: self._set_all(self.targets, False))
        self._rebuild()

    @staticmethod
    def _item(text, value, checked=False):
        item = QListWidgetItem(text)
        item.setData(Qt.UserRole, value)
        item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
        item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
        return item

    @staticmethod
    def _checked(widget):
        return [widget.item(i).data(Qt.UserRole) for i in range(widget.count()) if widget.item(i).checkState() == Qt.Checked]

    @staticmethod
    def _filter(widget, box):
        text = box.text().strip().lower()
        for i in range(widget.count()):
            widget.item(i).setHidden(bool(text) and text not in widget.item(i).text().lower())

    def _set_all(self, widget, value):
        widget.blockSignals(True)
        for i in range(widget.count()):
            if not widget.item(i).isHidden():
                widget.item(i).setCheckState(Qt.Checked if value else Qt.Unchecked)
        widget.blockSignals(False)
        self._summarize()

    def _rebuild(self, *_):
        side = self.side.currentData()
        self.formation_ids = [f for f in range(len(self.book.formations)) if formation_side(self.current, f) == side]
        self.keys, self.families = {}, {}
        for f in self.formation_ids:
            key, _name = formation_personnel(self.book, self.current, f)
            self.keys[f] = key
            self.families[f] = formation_family(self.source_book.formation_name(f) if f < len(self.source_book.formations) else self.book.formation_name(f)) if side == 0 else None
        for widget in (self.plays, self.personnel, self.family, self.targets):
            widget.blockSignals(True)
            widget.clear()
        for p in range(len(self.book.plays)):
            if play_side(self.current, p) == side:
                self.plays.addItem(self._item(f"{p}: {self.book.play_name(p)}", p))
        groups = {}
        for f in self.formation_ids:
            groups.setdefault(self.keys[f], []).append(f)
        for key in sorted(groups):
            names = sorted({formation_personnel(self.book, self.current, f)[1] for f in groups[key]})
            label = f"{key} personnel ({', '.join(names)}): {len(groups[key])} formations" if side == 0 else f"{key}: {len(groups[key])} formations"
            self.personnel.addItem(self._item(label, key))
        if side == 0:
            counts = {}
            for f in self.formation_ids:
                if self.families[f]:
                    counts[self.families[f]] = counts.get(self.families[f], 0) + 1
            for family in FAMILY_ORDER:
                if counts.get(family):
                    self.family.addItem(self._item(f"{family}: {counts[family]} formations", family))
        for f in self.formation_ids:
            self.targets.addItem(self._item(f"{f}: {self.book.formation_name(f)}  [{self.keys[f]}" + (f", {self.families[f]}]" if self.families[f] else "]"), f))
        for widget in (self.plays, self.personnel, self.family, self.targets):
            widget.blockSignals(False)
        self._summarize()

    def _matches(self):
        personnel, families = set(self._checked(self.personnel)), set(self._checked(self.family))
        if not personnel and not families:
            return set()
        out = set()
        for f in self.formation_ids:
            in_p, in_f = self.keys[f] in personnel, self.families[f] in families
            if (self.match.currentData() == "or" and (in_p or in_f)) or (
                    self.match.currentData() == "and" and (in_p or not personnel) and (in_f or not families)):
                out.add(f)
        return out

    def _apply_matches(self, additive):
        matches = self._matches()
        self.targets.blockSignals(True)
        for i in range(self.targets.count()):
            item = self.targets.item(i)
            if item.data(Qt.UserRole) in matches:
                item.setCheckState(Qt.Checked)
            elif not additive:
                item.setCheckState(Qt.Unchecked)
        self.targets.blockSignals(False)
        self._summarize()

    def _plan(self):
        current = {f: set(offered_plays(self.current, f)) for f in self.formation_ids}
        return assign_plays(current, self.locked, set(self._checked(self.plays)), self._checked(self.targets),
                            remove=self.operation.currentData() == "remove")

    def _summarize(self, *_):
        plays, formations = self._checked(self.plays), self._checked(self.targets)
        changed, skipped = self._plan()
        text = f"{len(plays)} plays, {len(formations)} formations selected: {len(changed)} formations would change."
        if skipped:
            what = "locked by your default playbook" if self.operation.currentData() == "remove" else "did not fit"
            text += f" {len(skipped)} formations have plays that {what} ({sum(skipped.values())} in all)."
        self.summary.setText(text)

    def request(self):
        changed, skipped = self._plan()
        self.notes = [f"{self.book.formation_name(f)}: {n} play(s) " + ("kept, in your default playbook" if self.operation.currentData() == "remove" else "did not fit")
                      for f, n in sorted(skipped.items())]
        return [{"formation": f, "plays": sorted(plays)} for f, plays in sorted(changed.items())]


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
        self.play_button, self.formation_button, self.cpu_button, self.offer_button, self.assign_button = [
            QPushButton(t) for t in ("Design Play…", "Design Formation…", "Add CPU call…", "Formation plays…", "Assign plays…")]
        for button in (self.play_button, self.formation_button, self.cpu_button, self.offer_button, self.assign_button):
            buttons.addWidget(button)
        self.offer_button.setToolTip("Choose the plays one formation offers in the in-game Playbook Manager (at most 84). "
                                     "Contributed by Basileus Maximus.")
        self.assign_button.setToolTip("Offer or stop offering plays in many formations at once, by personnel or family. "
                                      "Contributed by Basileus Maximus.")
        self.offer_button.clicked.connect(self._offers)
        self.assign_button.clicked.connect(self._assign)
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
        for button in (self.play_button, self.formation_button, self.cpu_button, self.offer_button, self.assign_button, self.stage_button, self.concept_button):
            button.setEnabled(value)
        self.stage_button.setEnabled(bool(value and self.draft and any(self.draft.get(k) for k in ("plays", "formations", "cpu_calls", "offer_sets"))))

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
        self.draft.setdefault("offer_sets", [])
        self.draft["unlock_offers"] = None  # the bulk unlock overfilled formations past the 84-play list limit
        self.dirty = False
        self._summary()
        self._enabled(True)

    def _next(self, kind):
        count = len(self.book.plays) if kind == "plays" else len(self.book.formations)
        return count + sum(r["mode"] == "append" for r in self.draft[kind])

    def _accept(self, draft):
        try:
            compile_design(self.source, draft)
        except (ValueError, ValidationError) as exc:
            QMessageBox.warning(self, "Cannot apply design", failure_body(exc))
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
        except (ValueError, ValidationError) as exc:
            QMessageBox.warning(self, "Cannot add concept", failure_body(exc))

    def _cpu(self):
        body = compile_design(self.source, self.draft).replacement if any(self.draft.get(k) for k in ("plays", "formations", "cpu_calls", "offer_sets")) else self.source
        dialog = CpuCallDialog(codec.Book.from_bytes(body), self.cpu_books, self)
        if dialog.exec_() == QDialog.Accepted:
            draft = copy.deepcopy(self.draft)
            draft["cpu_calls"].append(dialog.request())
            self._accept(draft)

    def _locked(self):
        """Plays each formation must keep offering: the default user playbook's plays (a missing bit crashes the manager)."""
        locked = {}
        book = self.cpu_books.get(1037)
        if book is not None:
            for row in book.records:
                for entry in row.entries:
                    locked.setdefault(row.formation_index, set()).add(entry.play_index)
        for call in self.draft["cpu_calls"]:
            if call["outer"] == 1037:
                locked.setdefault(call["formation"], set()).add(call["play"])
        return locked

    def _offers(self):
        try:
            changed = any(self.draft.get(k) for k in ("plays", "formations", "cpu_calls", "offer_sets"))
            body = compile_design(self.source, self.draft).replacement if changed else self.source
        except (ValueError, ValidationError) as exc:
            QMessageBox.warning(self, "Cannot open formation plays", failure_body(exc))
            return
        dialog = FormationOfferDialog(codec.Book.from_bytes(body), self.source, body, self._locked(), self)
        if dialog.exec_() != QDialog.Accepted:
            return
        self._merge_offers(dialog.request(), dialog.notes)

    def _assign(self):
        try:
            changed = any(self.draft.get(k) for k in ("plays", "formations", "cpu_calls", "offer_sets"))
            body = compile_design(self.source, self.draft).replacement if changed else self.source
        except (ValueError, ValidationError) as exc:
            QMessageBox.warning(self, "Cannot open assign plays", failure_body(exc))
            return
        dialog = AssignPlaysDialog(codec.Book.from_bytes(body), self.source, body, self._locked(), self)
        if dialog.exec_() == QDialog.Accepted:
            self._merge_offers(dialog.request(), dialog.notes)

    def _merge_offers(self, requested, notes):
        entries = {e["formation"]: e for e in self.draft["offer_sets"]}
        for entry in requested:
            entries[entry["formation"]] = entry
        original = struct.unpack_from(">I", self.source, 0x34)[0]
        for f in [f for f, e in entries.items() if f < original and e["plays"] == offered_plays(self.source, f)]:
            del entries[f]  # identical to retail: nothing to build
        draft = copy.deepcopy(self.draft)
        draft["offer_sets"] = [entries[f] for f in sorted(entries)]
        if self._accept(draft) and notes:
            QMessageBox.information(self, "Some plays were skipped", "\n".join(notes[:20]) + ("\n..." if len(notes) > 20 else ""))

    def _summary(self):
        self.summary.clear()
        for kind in ("plays", "formations"):
            for r in self.draft[kind]:
                self.summary.addItem(f"{r['mode'].title()} {kind[:-1]} {r['target']}: {r['name'] or 'keep name'}")
        for r in self.draft["cpu_calls"]:
            self.summary.addItem(f"CPU {r['outer']}, record {r['record']}: play {r['play']}, formation {r['formation']}")
        original = struct.unpack_from(">I", self.source, 0x34)[0]
        for e in self.draft.get("offer_sets", []):
            retail = set(offered_plays(self.source, e["formation"])) if e["formation"] < original else set()
            now = set(e["plays"])
            name = self.book.formation_name(e["formation"]) if e["formation"] < len(self.book.formations) else f"formation {e['formation']}"
            self.summary.addItem(f"Formation plays, {name}: {len(now)} offered (+{len(now - retail)} / -{len(retail - now)} vs retail)")
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
