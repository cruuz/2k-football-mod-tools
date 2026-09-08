"""Senior Bowl configuration and offline preview. No native launch is exposed."""
from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QAbstractItemView, QComboBox, QFileDialog, QFormLayout, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QMessageBox, QPushButton, QSpinBox,
    QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

from mod_editor.core import nfl2k5_senior_bowl as bowl


class SeniorBowlPanel(QWidget):
    settings_changed = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.players = ()
        self.event = None
        self._loading = False
        self._source_scheme = None
        layout = QVBoxLayout(self)
        label = QLabel(bowl.HELP_TEXT)
        label.setWordWrap(True)
        layout.addWidget(label)
        form = QFormLayout()
        self.source = QLineEdit()
        self.source.setReadOnly(True)
        row = QHBoxLayout()
        row.addWidget(self.source)
        self.open_button = QPushButton("Open franchise save")
        self.open_button.clicked.connect(self.open_save)
        row.addWidget(self.open_button)
        form.addRow("Source save", row)
        self.scheme = QComboBox()
        for key in bowl.SCHEMES:
            self.scheme.addItem(bowl.rr.SCHEME_TITLES[key], key)
        form.addRow("Position names", self.scheme)
        self.away = self._kits()
        self.home = self._kits()
        self.home.setCurrentIndex(3)
        form.addRow("Away kit", self.away)
        form.addRow("Home kit", self.home)
        self.seed = QSpinBox()
        self.seed.setRange(0, 2147483647)
        self.seed.setValue(1)
        form.addRow("Squad selection seed", self.seed)
        layout.addLayout(form)
        note = QLabel("Defaults use created-team kit bank 50 away and bank 51 home. "
                      "Bank 51 is an alternate donor. Appearance and contrast need in-game testing. "
                      "Opening or previewing a save changes no players, contracts or game files.")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.summary = QLabel("Open a signed SAVEGAME.DAT to preview the current rookie class.")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.tabs = QTabWidget()
        self.tables = []
        for title in ("Away squad", "Home squad", "Full class"):
            table = QTableWidget(0, 4)
            table.setHorizontalHeaderLabels(["Player", "Position", "Player index", "Senior Bowl"])
            table.setEditTriggers(QAbstractItemView.NoEditTriggers)
            table.setSelectionBehavior(QAbstractItemView.SelectRows)
            table.setSelectionMode(QAbstractItemView.SingleSelection)
            table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
            table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
            table.setSortingEnabled(True)
            self.tables.append(table)
            self.tabs.addTab(table, title)
        layout.addWidget(self.tabs)
        self.results = QLabel("No simulated result is available.")
        self.results.setWordWrap(True)
        layout.addWidget(self.results)
        controls = QHBoxLayout()
        for caption, callback in (("Save preview project", self.save_project), ("Open preview project", self.open_project)):
            button = QPushButton(caption)
            button.clicked.connect(callback)
            controls.addWidget(button)
        self.simulate_button = QPushButton("Simulate Senior Bowl (not available)")
        self.simulate_button.setEnabled(False)
        self.simulate_button.setToolTip(bowl.NATIVE_BLOCKER)
        controls.addWidget(self.simulate_button)
        layout.addLayout(controls)
        for widget in (self.scheme, self.away, self.home):
            widget.currentIndexChanged.connect(self._changed)
        self.seed.valueChanged.connect(self._changed)

    @staticmethod
    def _kits():
        combo = QComboBox()
        for bank, side in ((50, "A"), (50, "H"), (51, "A"), (51, "H")):
            combo.addItem(f"Bank {bank}, {'away' if side == 'A' else 'home'}, current", (bank, side, 0))
        return combo

    def settings(self):
        return bowl.Settings(self.scheme.currentData(), bowl.Kit(*self.away.currentData()),
                             bowl.Kit(*self.home.currentData())).validate()

    @staticmethod
    def _select_kit(combo, kit):
        wanted = (kit.bank, kit.side, kit.era)
        index = next(i for i in range(combo.count()) if tuple(combo.itemData(i)) == wanted)
        combo.setCurrentIndex(index)

    def options(self):
        # The shell persists this through its project settings, not a game save.
        return {"senior_bowl": False, "senior_bowl_settings": self.settings().to_dict(),
                "senior_bowl_seed": self.seed.value()}

    def set_options(self, value):
        bowl._require(type(value) is dict and set(value) == {"senior_bowl", "senior_bowl_settings", "senior_bowl_seed"}, "invalid Senior Bowl panel choices")
        bowl._require(value["senior_bowl"] is False, bowl.NATIVE_BLOCKER)
        settings = bowl.Settings.from_dict(value["senior_bowl_settings"])
        seed = bowl._integer(value["senior_bowl_seed"], 0, 2147483647, "panel seed")
        self._loading = True
        try:
            self.scheme.setCurrentIndex(self.scheme.findData(settings.scheme))
            self._select_kit(self.away, settings.away)
            self._select_kit(self.home, settings.home)
            self.seed.setValue(seed)
        finally:
            self._loading = False
        self.event = None
        self.refresh()

    def set_players(self, players, source=""):
        # Validate before replacing a visible preview. The signed-save reader is
        # used by open_save; this separate API supports Studio session snapshots.
        rows = tuple(players)
        bowl.current_class(rows, self.settings().scheme)
        self.players = rows
        self.source.setText(str(source))
        self._source_scheme = self.settings().scheme
        self.event = None
        self.refresh()

    def _changed(self, *_):
        if self._loading:
            return
        self.event = None
        self.refresh()
        try:
            self.settings_changed.emit(self.options())
        except ValueError:
            pass  # Refusal is visible in summary, no invalid choices are emitted.

    def selected_player_index(self, tab=None):
        table = self.tables[self.tabs.currentIndex() if tab is None else tab]
        item = table.item(table.currentRow(), 0)
        return None if item is None else item.data(Qt.UserRole)

    def _fill(self, table, players):
        table.setSortingEnabled(False)
        table.setRowCount(len(players))
        settings = self.settings()
        for row, p in enumerate(players):
            line = self.event.scouting_line(p.index) if self.event else None
            text = "No result" if line is None else "; ".join(f"{key.replace('_', ' ')} {value}" for key, value in line.items()
                                                           if key in bowl.PLAYER_STATS and value) or "Recorded: no counted stats"
            values = (p.name or f"Player {p.index}", bowl.rr.SCHEME_POSITION_NAMES[settings.scheme][p.position], p.index, text)
            for col, value in enumerate(values):
                item = QTableWidgetItem()
                item.setData(Qt.DisplayRole, value)
                item.setData(Qt.UserRole, p.index)
                table.setItem(row, col, item)
        table.setSortingEnabled(True)

    def refresh(self):
        for table in self.tables:
            table.setRowCount(0)
        self.results.setText("No simulated result is available.")
        try:
            settings = self.settings()
            if not self.players:
                self.summary.setText("Open a signed SAVEGAME.DAT to preview the current rookie class.")
                return
            rows = bowl.current_class(self.players, settings.scheme)
            self._fill(self.tables[2], rows)
            teams = bowl.select_squads(rows, seed=self.seed.value(), scheme=settings.scheme)
            for table, team in zip(self.tables, teams):
                self._fill(table, team)
            self.summary.setText(f"{len(rows)} eligible rookies; 53 players per squad. "
                                 f"{len(rows)-106} rookies are outside this game's squads. In-game event unavailable.")
            if self.event and self.event.state == "complete":
                self.results.setText(f"Development event result: Away {self.event.totals[0][0]}, Home {self.event.totals[1][0]}. "
                                     "This file is not an Xbox save or an in-game witness.")
        except (ValueError, TypeError) as exc:
            self.summary.setText(str(exc))

    def open_save(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open signed franchise save", "", "Xbox save (SAVEGAME.DAT)")
        if not path:
            return
        try:
            _document, players = bowl.read_franchise(path, scheme=self.settings().scheme)
            self.set_players(players, path)
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, "Senior Bowl", str(exc))

    def save_project(self):
        try:
            content = bowl.project_bytes(self.settings(), self.seed.value(), self.source.text(), self.event)
            path, _ = QFileDialog.getSaveFileName(self, "Save Senior Bowl preview project", "senior-bowl.2k5senior", "Senior Bowl preview (*.2k5senior)")
            if path:
                bowl._require(not self.source.text() or Path(path).resolve() != Path(self.source.text()).resolve(), "choose a separate project file")
                bowl.atomic_write(path, content)
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, "Senior Bowl", str(exc))

    def open_project(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open Senior Bowl preview project", "", "Senior Bowl preview (*.2k5senior)")
        if not path:
            return
        try:
            self.load_project(path)
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, "Senior Bowl", str(exc))

    def load_project(self, path):
        settings, seed, source, event = bowl.read_project(path)
        bowl._integer(seed, 0, 2147483647, "panel seed")
        players = ()
        if source and Path(source).is_file():
            _document, players = bowl.read_franchise(source, scheme=settings.scheme)
            if event:
                bowl._require(event.class_hash == bowl.class_fingerprint(players, settings.scheme), "project source now has a different rookie class")
        self.players = players
        self.set_options({"senior_bowl": False, "senior_bowl_settings": settings.to_dict(), "senior_bowl_seed": seed})
        self.source.setText(source)
        self.event = event
        self.refresh()
        if source and not players:
            self.summary.setText("Project choices loaded. The source save is missing; reopen it to rebuild the preview.")
