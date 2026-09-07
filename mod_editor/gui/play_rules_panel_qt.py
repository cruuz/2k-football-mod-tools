"""Retail assignment viewer and per-position bundle selection for the wizard."""
from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QAbstractItemView, QComboBox, QHBoxLayout, QLabel, QLineEdit,
                            QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from mod_editor.core import nfl2k5_play_library as lib, nfl2k5_play_rules as rules
from mod_editor.core.errors import ValidationError


class PlayRulesPanel(QWidget):
    def __init__(self, apply_bundle=None, reset=None, parent=None):
        super().__init__(parent)
        self.book = None
        self.body = None
        self._apply_bundle = apply_bundle
        self._reset = reset
        root = QVBoxLayout(self)
        notice = QLabel('Retail rules | EXPERIMENTAL / UNWITNESSED\n' + rules.RUNTIME_NOTICE)
        notice.setWordWrap(True)
        root.addWidget(notice)
        row = QHBoxLayout()
        self.presets = QComboBox()
        row.addWidget(QLabel('Rules library'))
        row.addWidget(self.presets, 1)
        root.addLayout(row)
        row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText('Search any play in the selected book')
        self.search.setClearButtonEnabled(True)
        self.plays = QComboBox()
        self.formations = QComboBox()
        row.addWidget(self.search, 1)
        row.addWidget(self.plays, 2)
        row.addWidget(self.formations, 1)
        root.addLayout(row)
        row = QHBoxLayout()
        self.scope = QComboBox()
        for label, value in [('All assignments', 'all'), ('Offensive line', 'line'), ('Active defense', 'active')]:
            self.scope.addItem(label, value)
        row.addWidget(QLabel('Copy positions'))
        row.addWidget(self.scope)
        self.apply = QPushButton('Apply selected rules')
        self.apply.setEnabled(False)
        self.reset = QPushButton('Reset copied rules')
        self.reset.setEnabled(reset is not None)
        row.addWidget(self.apply)
        row.addWidget(self.reset)
        row.addStretch()
        root.addLayout(row)
        self.positions = QTableWidget(1, 11)
        self.positions.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.positions.setMaximumHeight(90)
        self.positions.verticalHeader().hide()
        self.positions.setHorizontalHeaderLabels([str(s) for s in range(11)])
        root.addWidget(self.positions)
        self.nodes = QTableWidget(0, 5)
        self.nodes.setHorizontalHeaderLabels(['Position / slot', 'Node / pool index', 'Plain English', 'Opcode / flags', 'Exact bytes'])
        self.nodes.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.nodes.setWordWrap(True)
        self.nodes.setColumnWidth(0, 125)
        self.nodes.setColumnWidth(1, 115)
        self.nodes.setColumnWidth(2, 620)
        self.nodes.setColumnWidth(3, 115)
        self.nodes.horizontalHeader().setStretchLastSection(True)
        root.addWidget(self.nodes, 1)
        self.status = QLabel()
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        missing = QLabel('Inside Zone Read has no retail donor. Slide protection is runtime-only. '
                         'Combo Inside Zone is defensive coverage; it has no OL rules.')
        missing.setWordWrap(True)
        root.addWidget(missing)
        self.search.textChanged.connect(self._filter)
        self.plays.currentIndexChanged.connect(self._play_changed)
        self.formations.currentIndexChanged.connect(self._show)
        self.scope.currentIndexChanged.connect(self._select_scope)
        self.presets.currentIndexChanged.connect(self._preset)
        self.apply.clicked.connect(self.apply_selected)
        self.reset.clicked.connect(lambda: self._reset() if self._reset else None)

    def set_book(self, book, body):
        self.book, self.body = book, body
        self.presets.blockSignals(True)
        self.presets.clear()
        self.presets.addItem('Browse any retail play', None)
        for row in rules.catalog(book, body):
            self.presets.addItem(f"{row['label']} | {row['play_name']} | {row['formation_name']}", row)
        self.presets.blockSignals(False)
        self._filter()

    def _filter(self, *_args):
        self.plays.blockSignals(True)
        self.plays.clear()
        if self.book:
            query = self.search.text().casefold().split()
            for p in self.book.plays:
                if all(q in (p.name + ' ' + p.family_label + ' ' + str(p.index)).casefold() for q in query):
                    self.plays.addItem(f'{p.index}: {p.name} ({p.family_label})', p.index)
        self.plays.blockSignals(False)
        self._play_changed()

    def _preset(self, *_args):
        row = self.presets.currentData()
        if row is None:
            return
        self.search.clear()
        self.plays.setCurrentIndex(self.plays.findData(row['play']))
        self.formations.setCurrentIndex(self.formations.findData(row['formation']))
        self.scope.setCurrentIndex(self.scope.findData(row['scope']))
        self._select_scope()
        self.status.setText(row['note'] + ' Select both sides of any linked exchange.')

    def _play_changed(self, *_args):
        self.formations.blockSignals(True)
        self.formations.clear()
        if self.book:
            play = self.plays.currentData()
            for f in self.book.formations:
                if any(l.play_index == play for l in f.play_links):
                    self.formations.addItem(f'{f.index}: {f.name}', f.index)
        self.formations.blockSignals(False)
        self._show()

    def _show(self, *_args):
        self.nodes.setRowCount(0)
        self.positions.clearContents()
        play, formation = self.plays.currentData(), self.formations.currentData()
        self.apply.setEnabled(play is not None and formation is not None and self._apply_bundle is not None)
        if play is None:
            self.status.setText('No retail plays match this search.')
            return
        try:
            data = rules.inspect_play(self.book, self.body, play, formation)
            for slot in data['assignments']:
                item = QTableWidgetItem(slot['position'])
                item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Checked)
                self.positions.setItem(0, slot['slot'], item)
                for step, node in enumerate(slot['nodes']):
                    r = self.nodes.rowCount()
                    self.nodes.insertRow(r)
                    values = [f"{slot['position']} / {slot['slot']}", f"{step} / {node['index']}",
                              node['description'], f"{node['opcode']} / {node['flags']}", node['raw']]
                    for col, value in enumerate(values):
                        self.nodes.setItem(r, col, QTableWidgetItem(value))
            self.nodes.resizeRowsToContents()
            self._select_scope()
            self.status.setText(f"{data['family']}. All eleven declared chains are shown. " +
                ('No menu link: inspect only; personnel cannot be established.' if formation is None else
                 'Uncheck positions to copy a smaller bundle. Linked players must stay together.'))
        except (ValidationError, ValueError, IndexError) as exc:
            self.apply.setEnabled(False)
            self.status.setText(str(exc))

    def _select_scope(self, *_args):
        if self.book is None or self.plays.currentData() is None:
            return
        try:
            selected = self._scope_slots()
        except (ValidationError, ValueError, IndexError) as exc:
            self.apply.setEnabled(False)
            self.status.setText('These rules cannot be copied: ' + str(exc))
            return
        for slot in range(11):
            item = self.positions.item(0, slot)
            if item is not None:
                item.setCheckState(Qt.Checked if slot in selected else Qt.Unchecked)

    def _scope_slots(self):
        scope = self.scope.currentData()
        selected = set(range(11))
        if scope == 'line':
            f = self.formations.currentData()
            selected = set() if f is None else {s for s, code in enumerate(lib.category_positions(
                self.body, lib.formation_category(self.body, f))) if code & 31 in lib.OL_KINDS}
        elif scope == 'active':
            selected = (lib.defense_active(lib.exact_play_chains(self.body, self.plays.currentData()))
                        if self.book.plays[self.plays.currentData()].family_id == 1 else set())
        return set(rules.coupled_slots(lib.exact_play_chains(self.body, self.plays.currentData()), selected))

    def apply_selected(self):
        try:
            slots = tuple(s for s in range(11) if self.positions.item(0, s) is not None and
                          self.positions.item(0, s).checkState() == Qt.Checked)
            bundle = rules.extract_bundle(self.book, self.body, self.formations.currentData(),
                                           self.plays.currentData(), slots=slots)
            message = self._apply_bundle(bundle)
            self.status.setText(message)
        except (ValidationError, ValueError, TypeError, IndexError) as exc:
            self.status.setText('Rules were not applied: ' + str(exc))
