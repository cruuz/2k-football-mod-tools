"""The **Franchise** page of ★ Rosters: what Flying Finn's editor does with a franchise save, in our words.

It appears beside the roster only when the loaded Xbox save is a franchise save (``SAVEGAME.DAT`` of
720,044 bytes with the runtime arena at 0x2E0 and the season / front-office blocks after it) and it is
built entirely on ``mod_editor.core.nfl2k5_franchise_save``: every read is a property of
``FranchiseSave`` and every write is one of its writers (``set_display_year``, ``set_salary_cap``,
``set_user_control``, ``set_game``, ``set_coach_field``, ``place_on_injured_reserve``,
``activate_from_injured_reserve``).  No offset lives in this file; a region the core module marks
OPAQUE is never shown as editable.

**How edits are kept.**  The page holds a journal of ``FranchiseEdit`` records (kind, arguments, a
plain-words label) and a live ``FranchiseSave`` that is the loaded bytes with the journal applied.
Undo pops the journal and rebuilds the live save; redo re-applies.  That makes Undo per action and
gives the Checks tab its "what changed" list for free.

**Sharing bytes with the roster.**  A franchise save is also the roster the ★ Rosters page edits, and
the two overlap only in Finn's injured-reserve move (which compacts a team's pointer list inside the
arena).  So the roster document is the base: ``sync_from_roster`` takes ``document.to_body()`` (every
roster edit applied) and replays the journal on top of it; it runs when the page is shown, before an
injured-reserve move and before writing.  ``write_copy_to`` then hands the bytes to the container,
which re-signs ``EXTRA`` and copies every other member byte for byte — roster edits and franchise
edits land in one copy, in that order.

Finn's screens this covers (``FLYING_FINN_EDITOR_RE_2026-09-04.md`` §12): the year / user-control /
salary-cap dialogs, the schedule tab with its Edit Game and Swap Home/Away, the coach editor's
statistics, Back Field and Rating pages, and *Place on IR*.  Unwitnessed in game except where the core
module says otherwise (the year rule, the IR move); the activation is the unlabelled inverse.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mod_editor.core import nfl2k5_franchise_save as fs
from mod_editor.core import nfl2k5_roster_records as rr

# the coach numbers Finn's Statistics group edits, in his order, then the two ids and the playcalling split
COACH_STATS: tuple[tuple[str, str], ...] = (
    ("wins", "Wins"), ("losses", "Losses"), ("ties", "Ties"),
    ("seasons_with_team", "Seasons with team"), ("total_seasons", "Total seasons"),
    ("winning_seasons", "Winning seasons"), ("super_bowls", "Super Bowls"),
    ("super_bowl_wins", "Super Bowl wins"), ("super_bowl_losses", "Super Bowl losses"),
    ("playoff_wins", "Playoff wins"), ("playoff_losses", "Playoff losses"),
    ("season_wins", "This season: wins"), ("season_losses", "This season: losses"),
    ("season_ties", "This season: ties"),
    ("photo", "Photo id"), ("body", "Body"), ("playcalling_run", "Playcalling: run %"),
)
_CAPTIONS = {
    "qb": "QB", "rb": "RB", "te": "TE", "wr": "WR", "ol": "OL", "dl": "DL", "lb": "LB", "db": "DB",
    "rush_for": "Rush For", "pass_for": "Pass For", "i_form_run": "I Form: run", "i_form_pass": "I Form: pass",
}
YEAR_MIN, YEAR_MAX = fs.DISPLAY_YEAR_BASE, fs.DISPLAY_YEAR_BASE + 60           # the year field is a byte the core caps at 60
CAP_MAX_MILLIONS = 0x7FFFFFFF / 1000
GRID_ROW_TITLES = tuple(fs.ROW_NAMES.get(row, f"week {row + 1}").title() for row in range(fs.GRID_ROWS))
EDITABLE_HERE = (
    ("Season year", "PROVED", "display = 2004 + field, witnessed in game"),
    ("User-controlled teams", "PROVED", "FUN_000c4d70 reads the flags; Finn 0x913CC"),
    ("Salary cap", "PROVED", "DAT_00e3c278 in $1000 units; Finn 0x9ACCC"),
    ("Schedule cells", "PROVED", "the 22 x 17 grid; a played cell is refused unless you allow it; "
                                 "quarter-score side order is a HYPOTHESIS and stays read-only"),
    ("Coach record", "PROVED", "Finn's map, career numbers re-checked on real coaches; names are pooled strings and stay read-only"),
    ("Injured reserve: place", "PROVED", "Finn's 17-byte move reproduced byte for byte"),
    ("Injured reserve: activate", "HYPOTHESIS", "the inverse move, unwitnessed in game"),
)


def money(units: int) -> str:
    """$1000 units the way the game prints them: 88,113 -> $88.1M."""

    return f"${units / 1000:.1f}M"


def caption_for(name: str) -> str:
    return _CAPTIONS.get(name, name.replace("_", " ").title())


# --------------------------------------------------------------------------------------------- journal
@dataclass(frozen=True)
class FranchiseEdit:
    """One reversible franchise edit: which core writer, with what, and what it means in words."""

    kind: str
    label: str
    args: dict[str, Any] = field(default_factory=dict)

    def apply(self, save: fs.FranchiseSave) -> None:
        a = self.args
        if self.kind == "year":
            save.set_display_year(int(a["year"]))
        elif self.kind == "cap":
            save.set_salary_cap(int(a["value"]))
        elif self.kind == "control":
            save.set_user_control(int(a["team"]), bool(a["controlled"]))
        elif self.kind == "game":
            save.set_game(int(a["row"]), int(a["slot"]), allow_played=bool(a.get("allow_played", False)),
                          **{k: int(v) for k, v in dict(a["fields"]).items()})
        elif self.kind == "coach":
            save.set_coach_field(int(a["coach"]), str(a["name"]), int(a["value"]))
        elif self.kind == "ir_place":
            save.place_on_injured_reserve(int(a["team"]), int(a["player"]))
        elif self.kind == "ir_activate":
            save.activate_from_injured_reserve(int(a["team"]), int(a["player"]))
        else:
            raise fs.FranchiseSaveError(f"unknown franchise edit {self.kind!r}")


# --------------------------------------------------------------------------------------------- dialogs
class IrPickerDialog(QDialog):
    """Finn's *Place on IR*: pick one of the team's rostered players."""

    def __init__(self, team_label: str, rows: Sequence[tuple[int, str]], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Place on injured reserve — {team_label}")
        layout = QVBoxLayout(self)
        hint = QLabel("Choose the player. He leaves the team's list the way Finn's editor does it; "
                      "the game recomputes the team salary. Not yet tested in-game.")
        hint.setWordWrap(True)
        hint.setToolTip("His team's pointer list is compacted and its count drops by one, exactly Finn's move.")
        layout.addWidget(hint)
        self.list = QListWidget()
        for index, text in rows:
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, index)
            self.list.addItem(item)
        self.list.itemDoubleClicked.connect(lambda _item: self.accept())
        layout.addWidget(self.list, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.resize(420, 480)

    def chosen(self) -> int | None:
        item = self.list.currentItem()
        return None if item is None else int(item.data(Qt.UserRole))


# --------------------------------------------------------------------------------------------- the page
class FranchisePanel(QWidget):
    """The Franchise page: Overview, Schedule, Coaches, Injured Reserve, Checks."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._container: rr.SaveContainer | None = None
        self._document: rr.RosterDocument | None = None
        self._base = b""
        self._save: fs.FranchiseSave | None = None
        self._edits: list[FranchiseEdit] = []
        self._cursor = 0
        self._quiet = False
        self._players: dict[int, rr.Player] = {}
        self._coach_rows: list[int] = []
        self._coach_cards: dict[str, Any] = {}
        self._coach_spins: dict[str, QSpinBox] = {}
        self._host: QTabWidget | None = None
        self._host_index = -1
        self._checks_stale = True
        self._last_error = ""
        self._build()
        self._refresh_all()

    # ------------------------------------------------------------------ hosting
    def install(self, tabs: QTabWidget, title: str = "Franchise") -> int:
        """Add this page to the roster page's tab widget, hidden until a franchise save is loaded."""

        self._host = tabs
        self._host_index = tabs.addTab(self, title)
        self._set_tab_visible(False)
        return self._host_index

    def _set_tab_visible(self, visible: bool) -> None:
        if self._host is None:
            return
        if not visible and self._host.currentIndex() == self._host_index:
            self._host.setCurrentIndex(0)
        self._host.setTabVisible(self._host_index, visible)
        self._host.tabBar().setVisible(visible)

    @property
    def active(self) -> bool:
        return self._save is not None

    @property
    def save(self) -> fs.FranchiseSave | None:
        """The live franchise save (loaded bytes + every applied edit); None when no franchise save is loaded."""

        return self._save

    @property
    def edits(self) -> list[FranchiseEdit]:
        """The applied franchise edits since load, oldest first."""

        return list(self._edits[:self._cursor])

    # ------------------------------------------------------------------ construction
    def _build(self) -> None:
        layout = QVBoxLayout(self)
        header = QHBoxLayout()
        self.title_label = QLabel("")
        self.title_label.setWordWrap(True)
        font = self.title_label.font()
        font.setBold(True)
        self.title_label.setFont(font)
        header.addWidget(self.title_label, 1)
        self.dirty_label = QLabel("")
        self.dirty_label.setObjectName("franchise_dirty")
        header.addWidget(self.dirty_label)
        self.undo_button = QPushButton("Undo")
        self.undo_button.clicked.connect(self.undo)
        self.redo_button = QPushButton("Redo")
        self.redo_button.clicked.connect(self.redo)
        header.addWidget(self.undo_button)
        header.addWidget(self.redo_button)
        layout.addLayout(header)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_overview(), "Overview")
        self.tabs.addTab(self._build_schedule(), "Schedule")
        self.tabs.addTab(self._build_coaches(), "Coaches")
        self.tabs.addTab(self._build_injured_reserve(), "Injured Reserve")
        self.tabs.addTab(self._build_checks(), "Checks")
        self.tabs.currentChanged.connect(self._tab_changed)
        layout.addWidget(self.tabs, 1)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

    def _build_overview(self) -> QWidget:
        page = QWidget()
        box = QVBoxLayout(page)
        form = QFormLayout()
        year_row = QHBoxLayout()
        self.year_spin = QSpinBox()
        self.year_spin.setRange(YEAR_MIN, YEAR_MAX)
        self.year_spin.setKeyboardTracking(False)
        self.year_spin.setAccessibleName("Season year")
        self.year_spin.valueChanged.connect(self._year_changed)
        year_row.addWidget(self.year_spin)
        self.year_rule_label = QLabel("")
        year_row.addWidget(self.year_rule_label, 1)
        form.addRow("Season year", year_row)
        self.stage_label = QLabel("")
        form.addRow("Stage / week", self.stage_label)
        cap_row = QHBoxLayout()
        self.cap_spin = QDoubleSpinBox()
        self.cap_spin.setRange(0.001, CAP_MAX_MILLIONS)
        self.cap_spin.setDecimals(3)
        self.cap_spin.setSingleStep(0.5)
        self.cap_spin.setPrefix("$")
        self.cap_spin.setSuffix("M")
        self.cap_spin.setKeyboardTracking(False)
        self.cap_spin.setAccessibleName("Salary cap")
        self.cap_spin.valueChanged.connect(self._cap_changed)
        cap_row.addWidget(self.cap_spin)
        self.cap_raw_label = QLabel("")
        cap_row.addWidget(self.cap_raw_label, 1)
        self.cap_note = QLabel("Not yet tested in-game")
        self.cap_note.setObjectName("optionBadge")
        self.cap_note.setToolTip("Changing the cap writes the save's cap field; nobody has watched the game accept it yet.")
        cap_row.addWidget(self.cap_note)
        form.addRow("Salary cap", cap_row)
        box.addLayout(form)

        lists = QHBoxLayout()
        control_box = QGroupBox("User-controlled teams")
        control_layout = QVBoxLayout(control_box)
        self.control_list = QListWidget()
        self.control_list.setAccessibleName("User-controlled teams")
        self.control_list.itemChanged.connect(self._control_changed)
        control_layout.addWidget(self.control_list)
        lists.addWidget(control_box, 1)
        salary_box = QGroupBox("Team salary against the cap (read-only)")
        salary_box.setToolTip("The game recomputes every team's salary itself; this table only reads it.")
        salary_layout = QVBoxLayout(salary_box)
        self.salary_table = QTableWidget(0, 4)
        self.salary_table.setHorizontalHeaderLabels(["Team", "Salary", "Cap space", "Note"])
        self.salary_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.salary_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.salary_table.verticalHeader().setVisible(False)
        salary_layout.addWidget(self.salary_table)
        lists.addWidget(salary_box, 2)
        box.addLayout(lists, 1)
        return page

    def _build_schedule(self) -> QWidget:
        page = QWidget()
        box = QVBoxLayout(page)
        top = QHBoxLayout()
        top.addWidget(QLabel("Week"))
        self.week_combo = QComboBox()
        self.week_combo.addItems(list(GRID_ROW_TITLES))
        self.week_combo.setAccessibleName("Schedule week")
        self.week_combo.currentIndexChanged.connect(lambda _i: self._refresh_schedule())
        top.addWidget(self.week_combo)
        self.week_label = QLabel("")
        top.addWidget(self.week_label, 1)
        box.addLayout(top)
        self.schedule_table = QTableWidget(0, 7)
        self.schedule_table.setHorizontalHeaderLabels(["#", "Away", "Home", "Date", "Kick-off", "Played", "Score"])
        self.schedule_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.schedule_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.schedule_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.schedule_table.verticalHeader().setVisible(False)
        self.schedule_table.itemSelectionChanged.connect(self._schedule_row_selected)
        box.addWidget(self.schedule_table, 1)

        editor = QGroupBox("Edit the selected game")
        grid = QGridLayout(editor)
        self.away_combo = QComboBox()
        self.away_combo.setAccessibleName("Away team")
        self.home_combo = QComboBox()
        self.home_combo.setAccessibleName("Home team")
        self.month_spin = QSpinBox()
        self.month_spin.setRange(1, 12)
        self.month_spin.setAccessibleName("Month")
        self.day_spin = QSpinBox()
        self.day_spin.setRange(1, 31)
        self.day_spin.setAccessibleName("Day")
        self.hour_spin = QSpinBox()
        self.hour_spin.setRange(0, 12)
        self.hour_spin.setAccessibleName("Hour")
        self.hour_spin.setToolTip("The game's hour byte: 0 prints as 12")
        self.minute_spin = QSpinBox()
        self.minute_spin.setRange(0, 59)
        self.minute_spin.setAccessibleName("Minute")
        grid.addWidget(QLabel("Away"), 0, 0)
        grid.addWidget(self.away_combo, 0, 1)
        grid.addWidget(QLabel("at Home"), 0, 2)
        grid.addWidget(self.home_combo, 0, 3)
        grid.addWidget(QLabel("Date (month / day)"), 1, 0)
        date_row = QHBoxLayout()
        date_row.addWidget(self.month_spin)
        date_row.addWidget(self.day_spin)
        grid.addLayout(date_row, 1, 1)
        grid.addWidget(QLabel("Kick-off (hour / minute)"), 1, 2)
        time_row = QHBoxLayout()
        time_row.addWidget(self.hour_spin)
        time_row.addWidget(self.minute_spin)
        grid.addLayout(time_row, 1, 3)
        buttons = QHBoxLayout()
        self.apply_game_button = QPushButton("Apply to this game")
        self.apply_game_button.clicked.connect(self._apply_game_clicked)
        self.swap_button = QPushButton("Swap home/away")
        self.swap_button.clicked.connect(self._swap_clicked)
        self.allow_played_check = QCheckBox("Allow editing played games")
        self.allow_played_check.setToolTip("A played cell carries its score and flags; the page refuses to "
                                           "change it unless you tick this")
        buttons.addWidget(self.apply_game_button)
        buttons.addWidget(self.swap_button)
        buttons.addWidget(self.allow_played_check)
        schedule_note = QLabel("Not yet tested in-game")
        schedule_note.setObjectName("optionBadge")
        schedule_note.setToolTip("Schedule edits write the save's grid cells (scores stay read-only); "
                                 "nobody has watched the game accept them yet.")
        buttons.addWidget(schedule_note)
        buttons.addStretch(1)
        grid.addLayout(buttons, 2, 0, 1, 4)
        box.addWidget(editor)
        return page

    def _build_coaches(self) -> QWidget:
        from mod_editor.gui.roster_editor_panel_qt import AttributeCard      # the player cards' bar, lazily

        page = QSplitter(Qt.Horizontal)
        self.coach_list = QListWidget()
        self.coach_list.setAccessibleName("Coaches")
        self.coach_list.currentRowChanged.connect(lambda _row: self._refresh_coach())
        page.addWidget(self.coach_list)

        area = QScrollArea()
        area.setWidgetResizable(True)
        host = QWidget()
        box = QVBoxLayout(host)
        coach_note = QLabel("Coach edits: not yet tested in-game. Names and info lines are read-only (pooled text).")
        coach_note.setWordWrap(True)
        box.addWidget(coach_note)
        self.coach_name_label = QLabel("")
        font = self.coach_name_label.font()
        font.setPointSizeF(font.pointSizeF() + 3)
        font.setBold(True)
        self.coach_name_label.setFont(font)
        box.addWidget(self.coach_name_label)
        self.coach_info_label = QLabel("")
        self.coach_info_label.setWordWrap(True)
        box.addWidget(self.coach_info_label)
        self.coach_teams_label = QLabel("")
        box.addWidget(self.coach_teams_label)

        stats = QGroupBox("Statistics")
        stats_grid = QGridLayout(stats)
        for position, (name, caption) in enumerate(COACH_STATS):
            spin = QSpinBox()
            rel, fmt = fs.COACH_FIELDS[name]
            high = 100 if name == "playcalling_run" else (0xFFFF if fmt == "<H" else 0x7FFFFFFF)
            spin.setRange(0, high)
            spin.setKeyboardTracking(False)
            spin.setAccessibleName(f"Coach {caption}")
            spin.valueChanged.connect(lambda value, n=name: self._coach_value_changed(n, value))
            self._coach_spins[name] = spin
            row, column = divmod(position, 3)
            stats_grid.addWidget(QLabel(caption), row, column * 2)
            stats_grid.addWidget(spin, row, column * 2 + 1)
        box.addWidget(stats)

        ratings = QGroupBox("Rating (the 23 coach ratings)")
        ratings_grid = QGridLayout(ratings)
        for position, name in enumerate(fs.COACH_RATINGS):
            card = AttributeCard(name, caption_for(name), 0, 99)
            card.changed.connect(self._coach_value_changed)
            self._coach_cards[name] = card
            row, column = divmod(position, 4)
            ratings_grid.addWidget(card, row, column)
        box.addWidget(ratings)

        tendencies = QGroupBox("Back Field (run / pass tendency per formation, %)")
        tendencies_grid = QGridLayout(tendencies)
        for position, name in enumerate(fs.COACH_TENDENCIES):
            card = AttributeCard(name, caption_for(name), 0, 100)
            card.changed.connect(self._coach_value_changed)
            self._coach_cards[name] = card
            row, column = divmod(position, 4)
            tendencies_grid.addWidget(card, row, column)
        box.addWidget(tendencies)
        box.addStretch(1)
        area.setWidget(host)
        page.addWidget(area)
        page.setStretchFactor(0, 1)
        page.setStretchFactor(1, 3)
        return page

    def _build_injured_reserve(self) -> QWidget:
        page = QWidget()
        box = QVBoxLayout(page)
        top = QHBoxLayout()
        top.addWidget(QLabel("Team"))
        self.ir_team_combo = QComboBox()
        self.ir_team_combo.setAccessibleName("Injured reserve team")
        self.ir_team_combo.currentIndexChanged.connect(lambda _i: self._refresh_injured_reserve())
        top.addWidget(self.ir_team_combo)
        self.place_ir_button = QPushButton("Place on IR…")
        self.place_ir_button.clicked.connect(self._place_ir_clicked)
        self.activate_ir_button = QPushButton("Activate")
        self.activate_ir_button.setToolTip("The inverse of Finn's move: the player rejoins the end of the team's "
                                           "list and the slot is cleared. Nobody has watched the game accept it yet.")
        self.activate_ir_button.clicked.connect(self._activate_ir_clicked)
        top.addWidget(self.place_ir_button)
        top.addWidget(self.activate_ir_button)
        activate_note = QLabel("Not yet tested in-game")
        activate_note.setObjectName("optionBadge")
        activate_note.setToolTip(self.activate_ir_button.toolTip())
        top.addWidget(activate_note)
        top.addStretch(1)
        box.addLayout(top)
        self.ir_table = QTableWidget(fs.IR_SLOTS, 3)
        self.ir_table.setHorizontalHeaderLabels(["Slot", "Player", "Player index"])
        self.ir_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.ir_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.ir_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.ir_table.verticalHeader().setVisible(False)
        box.addWidget(self.ir_table)
        note = QLabel("Place on IR moves the player the way Finn's editor does; the game recomputes the team "
                      "salary (IR still counts against the cap). A free agent or a draft prospect cannot go on IR.")
        note.setWordWrap(True)
        note.setToolTip("Byte for byte Finn's move: the team's pointer list is compacted, the count byte drops by one, "
                        "the player is marked injured reserve and the first free of the team's five slots takes him.")
        box.addWidget(note)
        league = QGroupBox("Everyone on injured reserve")
        league_layout = QVBoxLayout(league)
        self.league_ir_list = QListWidget()
        league_layout.addWidget(self.league_ir_list)
        box.addWidget(league, 1)
        return page

    def _build_checks(self) -> QWidget:
        page = QWidget()
        box = QVBoxLayout(page)
        top = QHBoxLayout()
        self.checks_refresh_button = QPushButton("Refresh")
        self.checks_refresh_button.clicked.connect(lambda: self._refresh_checks(force=True))
        top.addWidget(self.checks_refresh_button)
        top.addWidget(QLabel("What is proved about this save's layout, what this page may edit, and every "
                             "franchise edit since load in plain words."), 1)
        box.addLayout(top)
        self.checks_text = QPlainTextEdit()
        self.checks_text.setReadOnly(True)
        box.addWidget(self.checks_text, 1)
        return page

    # ------------------------------------------------------------------ loading
    def load(self, container: rr.SaveContainer, document: rr.RosterDocument) -> bool:
        """Adopt a save; returns False (and stays hidden) unless it is a franchise save."""

        self.clear()
        if not fs.is_franchise_save(container.savegame):
            return False
        self._container = container
        self._document = document
        self._base = bytes(container.savegame)
        self._save = fs.FranchiseSave(self._base, container=container, source=str(container.path))
        self._players = {p.index: p for p in document.players if p.pool == "primary"}
        self._populate_static()
        self._refresh_all(force_checks=True)
        self._set_tab_visible(True)
        self._set_status(f"Franchise save: {self._save.one_line()}")
        return True

    def clear(self) -> None:
        self._container = None
        self._document = None
        self._base = b""
        self._save = None
        self._edits = []
        self._cursor = 0
        self._players = {}
        self._last_error = ""
        self._set_tab_visible(False)
        self._refresh_all(force_checks=True)
        self._set_status("")

    def showEvent(self, event) -> None:  # noqa: N802 - Qt naming
        super().showEvent(event)
        if self.active:
            self.sync_from_roster()

    def sync_from_roster(self) -> bool:
        """Take the roster page's edits as the base and replay the franchise edits on top of them."""

        if self._save is None or self._document is None:
            return False
        try:
            body = self._document.to_body()
        except Exception as exc:  # noqa: BLE001 - one message, the roster page's own write shows the same
            self._last_error = f"the roster edits could not be applied first: {type(exc).__name__}: {exc}"
            self._set_status(f"Refused: {self._last_error}")
            return False
        if len(body) != len(self._base):
            self._last_error = "the roster arena changed size"
            self._set_status(f"Refused: {self._last_error}")
            return False
        if body != self._base:
            self._base = body
            self._rebuild()
            self._refresh_all()
        return True

    # ------------------------------------------------------------------ the journal
    def _fresh_save(self) -> fs.FranchiseSave:
        assert self._container is not None
        return fs.FranchiseSave(self._base, container=self._container, source=str(self._container.path))

    def _rebuild(self) -> None:
        """The live save = base + edits[:cursor].  An edit the roster pulled the rug from under is dropped and said."""

        save = self._fresh_save()
        applied = 0
        for edit in self._edits[:self._cursor]:
            try:
                edit.apply(save)
            except (fs.FranchiseSaveError, rr.RosterRecordError) as exc:
                self._set_status(f"Dropped a franchise edit the roster changed underneath: {edit.label} ({exc})")
                break
            applied += 1
        if applied != self._cursor:
            del self._edits[applied:]
            self._cursor = applied
        self._save = save

    def push(self, edit: FranchiseEdit) -> bool:
        """Apply one edit to the live save and journal it; a refusal restores the live save and says why."""

        if self._save is None:
            return False
        try:
            edit.apply(self._save)
        except (fs.FranchiseSaveError, rr.RosterRecordError) as exc:
            self._last_error = str(exc)
            self._rebuild()                                     # set_game can have written a byte before refusing
            self._refresh_all()
            self._set_status(f"Refused: {exc}")
            return False
        del self._edits[self._cursor:]
        self._edits.append(edit)
        self._cursor += 1
        self._checks_stale = True
        self._refresh_all()
        self._set_status(edit.label)
        return True

    def undo(self) -> str:
        if self._cursor == 0:
            return ""
        self._cursor -= 1
        label = self._edits[self._cursor].label
        self._rebuild()
        self._checks_stale = True
        self._refresh_all()
        self._set_status(f"Undid: {label}")
        return label

    def redo(self) -> str:
        if self._cursor >= len(self._edits) or self._save is None:
            return ""
        edit = self._edits[self._cursor]
        try:
            edit.apply(self._save)
        except (fs.FranchiseSaveError, rr.RosterRecordError) as exc:
            del self._edits[self._cursor:]
            self._rebuild()
            self._refresh_all()
            self._set_status(f"Could not redo {edit.label}: {exc}")
            return ""
        self._cursor += 1
        self._checks_stale = True
        self._refresh_all()
        self._set_status(f"Redid: {edit.label}")
        return edit.label

    def edit_labels(self) -> list[str]:
        return [edit.label for edit in self._edits[:self._cursor]]

    # ------------------------------------------------------------------ writing
    def write_copy_to(self, target: Path | str, *, overwrite: bool = False) -> dict[str, Any]:
        """Roster edits first, then the franchise edits, into ONE re-signed copy.  Never the source."""

        if self._save is None or self._container is None:
            raise fs.FranchiseSaveError("no franchise save is loaded")
        if not self.sync_from_roster():
            raise fs.FranchiseSaveError(self._last_error or "the roster edits could not be applied")
        receipt = self._save.write(target, overwrite=overwrite)
        receipt["franchise_edits"] = self.edit_labels()
        receipt["franchise_changed_ranges"] = [(start, end) for start, end in self._save.changed_ranges()]
        return receipt

    # ------------------------------------------------------------------ names
    def _team_label(self, index: int) -> str:
        if self._save is None:
            return f"team {index}"
        if index < self._save.league_team_count:
            abbreviation = self._save.team_abbreviation(index)
            display = ""
            if self._document is not None and index < len(self._document.teams):
                display = self._document.teams[index].display
            return f"{abbreviation} · {display}" if display and display != abbreviation else abbreviation
        return self._save.team_abbreviation(index)

    def _team_short(self, index: int) -> str:
        return self._save.team_abbreviation(index) if self._save is not None else f"team {index}"

    def _player_text(self, index: int) -> str:
        if self._save is None:
            return f"#{index}"
        player = self._players.get(index)
        if player is not None:
            return f"{player.record.position_name} {player.display} (#{index})"
        name = self._save.player_name(index)
        return f"{name} (#{index})" if name else f"#{index}"

    # ------------------------------------------------------------------ static lists
    def _populate_static(self) -> None:
        assert self._save is not None
        self._quiet = True
        try:
            self.control_list.clear()
            for team in range(self._save.league_team_count):
                item = QListWidgetItem(self._team_label(team))
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setData(Qt.UserRole, team)
                item.setCheckState(Qt.Unchecked)
                self.control_list.addItem(item)
            for combo in (self.home_combo, self.away_combo):
                combo.clear()
                for team in range(fs.LEAGUE_SLOTS):
                    combo.addItem(self._team_label(team), team)
            self.ir_team_combo.clear()
            for team in range(self._save.league_team_count):
                self.ir_team_combo.addItem(self._team_label(team), team)
            self.coach_list.clear()
            self._coach_rows = []
            coaches = self._save.coaches()
            attached = [c for c in coaches if c.teams]
            attached.sort(key=lambda c: min(c.teams))
            for coach in attached + [c for c in coaches if not c.teams]:
                teams = ", ".join(self._team_short(t) for t in coach.teams) or "no team"
                self.coach_list.addItem(f"{coach.name or f'coach {coach.index}'} — {teams}")
                self._coach_rows.append(coach.index)
            if self._coach_rows:
                self.coach_list.setCurrentRow(0)
            self.week_combo.setCurrentIndex(max(0, min(self._save.header.week, fs.GRID_ROWS - 1))
                                            if self._save.header.stage == 8 else 0)
        finally:
            self._quiet = False

    # ------------------------------------------------------------------ refresh
    def _refresh_all(self, *, force_checks: bool = False) -> None:
        self._refresh_header()
        self._refresh_overview()
        self._refresh_schedule()
        self._refresh_coach()
        self._refresh_injured_reserve()
        if force_checks or self.tabs.currentIndex() == 4:
            self._refresh_checks(force=True)
        else:
            self._checks_stale = True

    def _tab_changed(self, index: int) -> None:
        if index == 4 and self._checks_stale:
            self._refresh_checks(force=True)

    def _refresh_header(self) -> None:
        loaded = self._save is not None
        self.setEnabled(loaded)
        self.title_label.setText(self._save.one_line() if loaded else "No franchise save loaded.")
        count = self._cursor
        self.dirty_label.setText(f"● {count} franchise edit{'s' if count != 1 else ''} (not yet written)" if count else "")
        self.undo_button.setEnabled(loaded and self._cursor > 0)
        self.redo_button.setEnabled(loaded and self._cursor < len(self._edits))
        self.undo_button.setToolTip(f"Undo: {self._edits[self._cursor - 1].label}" if self._cursor else "")
        self.redo_button.setToolTip(f"Redo: {self._edits[self._cursor].label}" if self._cursor < len(self._edits) else "")

    def _refresh_overview(self) -> None:
        self._quiet = True
        try:
            if self._save is None:
                self.year_spin.setValue(YEAR_MIN)
                self.year_rule_label.setText("")
                self.stage_label.setText("")
                self.cap_spin.setValue(0.001)
                self.cap_raw_label.setText("")
                self.salary_table.setRowCount(0)
                return
            header = self._save.header
            self.year_spin.setValue(header.display_year)
            self.year_rule_label.setText(f"= 2004 + year field {header.year_field} (the game's own rule, witnessed in game)")
            self.stage_label.setText(f"{header.stage_name}, week {header.week}/{header.stage_weeks} "
                                     f"(stage {header.stage}; read-only)")
            cap = self._save.salary_cap
            self.cap_spin.setValue(cap / 1000)
            self.cap_raw_label.setText(f"raw {cap:,} ($1000 units, the value the game stores)")
            users = set(self._save.user_teams())
            for row in range(self.control_list.count()):
                item = self.control_list.item(row)
                item.setCheckState(Qt.Checked if int(item.data(Qt.UserRole)) in users else Qt.Unchecked)
            seasons = self._save.team_seasons()
            self.salary_table.setRowCount(len(seasons))
            for row, season in enumerate(seasons):
                space = cap - season.salary
                cells = [self._team_label(season.index), f"{money(season.salary)} ({season.salary:,})",
                         f"{'-' if space < 0 else ''}{money(abs(space))}",
                         "over the cap" if space < 0 else ("user-controlled" if season.index in users else "")]
                for column, text in enumerate(cells):
                    self.salary_table.setItem(row, column, QTableWidgetItem(text))
            self.salary_table.resizeColumnsToContents()
        finally:
            self._quiet = False

    def _refresh_schedule(self) -> None:
        self._quiet = True
        try:
            if self._save is None:
                self.schedule_table.setRowCount(0)
                self.week_label.setText("")
                return
            row = self.week_combo.currentIndex()
            games = self._save.games(rows=[row]) if row >= 0 else []
            selected = self.schedule_table.currentRow()
            self.schedule_table.setRowCount(len(games))
            for line, game in enumerate(games):
                score = ""
                tip = ""
                if game.scores is not None:
                    first, second = game.scores
                    score = f"{sum(first)} – {sum(second)}"
                    tip = (f"quarters {'-'.join(map(str, first))} / {'-'.join(map(str, second))}; which side is "
                           f"which is a HYPOTHESIS, so scores stay read-only")
                cells = [str(game.slot + 1), self._team_short(game.away), self._team_short(game.home),
                         f"{game.month}/{game.day}", game.kickoff(), "yes" if game.played else "", score]
                for column, text in enumerate(cells):
                    item = QTableWidgetItem(text)
                    if tip and column == 6:
                        item.setToolTip(tip)
                    item.setData(Qt.UserRole, game.slot)
                    self.schedule_table.setItem(line, column, item)
            self.schedule_table.resizeColumnsToContents()
            played = sum(1 for g in games if g.played)
            self.week_label.setText(f"{len(games)} games, {played} played")
            if 0 <= selected < len(games):
                self.schedule_table.selectRow(selected)
            self._fill_game_editor()
        finally:
            self._quiet = False

    def _selected_game(self) -> fs.Game | None:
        if self._save is None:
            return None
        row = self.week_combo.currentIndex()
        line = self.schedule_table.currentRow()
        item = self.schedule_table.item(line, 0) if line >= 0 else None
        if item is None:
            return None
        return self._save.game(row, int(item.data(Qt.UserRole)))

    def _schedule_row_selected(self) -> None:
        if not self._quiet:
            self._fill_game_editor()

    def _fill_game_editor(self) -> None:
        game = self._selected_game()
        was_quiet = self._quiet
        self._quiet = True
        try:
            enabled = game is not None
            for widget in (self.home_combo, self.away_combo, self.month_spin, self.day_spin, self.hour_spin,
                           self.minute_spin, self.apply_game_button, self.swap_button):
                widget.setEnabled(enabled)
            if game is None:
                return
            self.home_combo.setCurrentIndex(self.home_combo.findData(game.home))
            self.away_combo.setCurrentIndex(self.away_combo.findData(game.away))
            self.month_spin.setValue(max(1, game.month))
            self.day_spin.setValue(max(1, game.day))
            self.hour_spin.setValue(game.hour)
            self.minute_spin.setValue(game.minute)
        finally:
            self._quiet = was_quiet

    def _refresh_coach(self) -> None:
        self._quiet = True
        try:
            coach = self._current_coach()
            enabled = coach is not None
            for spin in self._coach_spins.values():
                spin.setEnabled(enabled)
            for card in self._coach_cards.values():
                card.setEnabled(enabled)
            if coach is None:
                self.coach_name_label.setText("No coach selected." if self._save is not None else "")
                self.coach_info_label.setText("")
                self.coach_teams_label.setText("")
                return
            self.coach_name_label.setText(coach.name or f"coach {coach.index}")
            self.coach_info_label.setText(" / ".join(line for line in coach.info if line) or "(no info lines)")
            teams = ", ".join(self._team_label(t) for t in coach.teams) or "not attached to a team"
            self.coach_teams_label.setText(f"Coach record {coach.index} · {teams} · names and info lines are pooled "
                                           f"strings and stay read-only")
            for name, spin in self._coach_spins.items():
                spin.setValue(coach.fields[name])
            for name, card in self._coach_cards.items():
                card.set_value(coach.ratings[name] if name in coach.ratings else coach.tendencies[name])
        finally:
            self._quiet = False

    def _current_coach(self) -> fs.Coach | None:
        if self._save is None:
            return None
        row = self.coach_list.currentRow()
        if not 0 <= row < len(self._coach_rows):
            return None
        wanted = self._coach_rows[row]
        for coach in self._save.coaches():
            if coach.index == wanted:
                return coach
        return None

    def _refresh_injured_reserve(self) -> None:
        self._quiet = True
        try:
            self.league_ir_list.clear()
            for row in range(fs.IR_SLOTS):
                for column in range(3):
                    self.ir_table.setItem(row, column, QTableWidgetItem(""))
            if self._save is None:
                self.place_ir_button.setEnabled(False)
                self.activate_ir_button.setEnabled(False)
                return
            team = self._ir_team()
            entries = {e.slot: e for e in self._save.injured_reserve(include_empty=True) if e.team == team}
            for slot in range(fs.IR_SLOTS):
                entry = entries.get(slot)
                empty = entry is None or entry.player_index == fs.IR_EMPTY
                cells = [str(slot + 1), "(empty)" if empty else (entry.name or f"#{entry.player_index}"),
                         "" if empty else str(entry.player_index)]
                for column, text in enumerate(cells):
                    self.ir_table.setItem(slot, column, QTableWidgetItem(text))
            self.ir_table.resizeColumnsToContents()
            for entry in self._save.injured_reserve():
                self.league_ir_list.addItem(f"{self._team_label(entry.team)}: {entry.name or f'#{entry.player_index}'} "
                                            f"(slot {entry.slot + 1}, player #{entry.player_index})")
            self.place_ir_button.setEnabled(True)
            self.activate_ir_button.setEnabled(any(e.player_index != fs.IR_EMPTY for e in entries.values()))
        finally:
            self._quiet = False

    def _ir_team(self) -> int:
        data = self.ir_team_combo.currentData()
        return int(data) if data is not None else 0

    def checks_text_for(self) -> str:
        """The Checks page as text: the region map by status, what is editable here, the edits, the byte diff."""

        if self._save is None:
            return "No franchise save loaded."
        lines = [f"Franchise save: {self._save.source}", self._save.one_line(), "",
                 "Layout map (mod_editor/core/nfl2k5_franchise_save.py, REGIONS; tiles the file with no gap):"]
        for status in ("PROVED", "HYPOTHESIS", "OPAQUE"):
            regions = [r for r in fs.REGIONS if r.status == status]
            total = sum(r.size for r in regions)
            note = {"PROVED": "read off the game's own save / restore routines or witnessed",
                    "HYPOTHESIS": "layout known, meaning believed; shown read-only",
                    "OPAQUE": "carried byte for byte, never shown as editable"}[status]
            lines.append(f"  {status}: {len(regions)} regions, {total:,} bytes — {note}")
            for region in regions:
                extra = f" — {region.note}" if region.note else ""
                lines.append(f"    0x{region.offset:06X}..0x{region.end:06X}  {region.label}{extra}")
        lines.append("")
        lines.append("Editable on this page:")
        for what, status, why in EDITABLE_HERE:
            lines.append(f"  {what}: {status} — {why}")
        lines.append("")
        labels = self.edit_labels()
        lines.append(f"Franchise edits since load ({len(labels)}):")
        lines.extend(f"  {n}. {label}" for n, label in enumerate(labels, 1))
        if not labels:
            lines.append("  none")
        ranges = self._save.changed_ranges()
        total = sum(end - start for start, end in ranges)
        lines.append("")
        lines.append(f"Bytes that differ from the loaded save with the roster edits applied: {len(ranges)} "
                     f"range{'s' if len(ranges) != 1 else ''}, {total:,} byte{'s' if total != 1 else ''}")
        for start, end in ranges:
            region = next((r for r in fs.REGIONS if r.offset <= start < r.end), None)
            where = f"{region.label} [{region.status}]" if region else "outside the map"
            lines.append(f"  0x{start:06X}..0x{end:06X} ({end - start} B) — {where}")
        return "\n".join(lines)

    def _refresh_checks(self, *, force: bool = False) -> None:
        if not force and not self._checks_stale:
            return
        self.checks_text.setPlainText(self.checks_text_for())
        self._checks_stale = False

    # ------------------------------------------------------------------ overview edits
    def _year_changed(self, year: int) -> None:
        if self._quiet or self._save is None:
            return
        before = self._save.header.display_year
        if before == year:
            return
        self.push(FranchiseEdit("year", f"Season year {before} → {year} (year field {year - fs.DISPLAY_YEAR_BASE})",
                                {"year": year}))

    def _cap_changed(self, millions: float) -> None:
        if self._quiet or self._save is None:
            return
        value = int(round(millions * 1000))
        before = self._save.salary_cap
        if value == before:
            return
        self.push(FranchiseEdit("cap", f"Salary cap {money(before)} ({before:,}) → {money(value)} ({value:,})",
                                {"value": value}))

    def _control_changed(self, item: QListWidgetItem) -> None:
        if self._quiet or self._save is None:
            return
        team = int(item.data(Qt.UserRole))
        controlled = item.checkState() == Qt.Checked
        if (team in self._save.user_teams()) == controlled:
            return
        self.push(FranchiseEdit("control", f"{self._team_short(team)}: {'CPU → user-controlled' if controlled else 'user-controlled → CPU'}",
                                {"team": team, "controlled": controlled}))

    def set_year(self, year: int) -> bool:
        self.year_spin.setValue(year)
        return self._save is not None and self._save.header.display_year == year

    def set_salary_cap(self, units: int) -> bool:
        if self._save is None:
            return False
        self.cap_spin.setValue(units / 1000)
        return self._save.salary_cap == units

    def set_user_control(self, team: int, controlled: bool) -> bool:
        for row in range(self.control_list.count()):
            item = self.control_list.item(row)
            if int(item.data(Qt.UserRole)) == team:
                item.setCheckState(Qt.Checked if controlled else Qt.Unchecked)
                return self._save is not None and ((team in self._save.user_teams()) == controlled)
        return False

    # ------------------------------------------------------------------ schedule edits
    def edit_game(self, row: int, slot: int, **fields: int) -> bool:
        """Change a grid cell through ``set_game``; a played cell needs the checkbox and says so otherwise."""

        if self._save is None:
            return False
        try:
            game = self._save.game(row, slot)
        except fs.FranchiseSaveError as exc:
            self._set_status(f"Refused: {exc}")
            return False
        allow = self.allow_played_check.isChecked()
        if game.played and not allow:
            self._last_error = ("this game has been played (its score and flags are in the save); tick "
                                "'Allow editing played games' to change it anyway")
            self._set_status(f"Refused: {self._last_error}")
            return False
        current = {"home": game.home, "away": game.away, "month": game.month, "day": game.day,
                   "hour": game.hour, "minute": game.minute, "slot_code": game.slot_code}
        changes = {name: int(value) for name, value in fields.items() if name in current and int(value) != current[name]}
        if not changes:
            self._set_status("Nothing to change on that game.")
            return False
        words = []
        for name, value in changes.items():
            if name in ("home", "away"):
                words.append(f"{name} {self._team_short(current[name])} → {self._team_short(value)}")
            else:
                words.append(f"{name} {current[name]} → {value}")
        label = f"{GRID_ROW_TITLES[row]} game {slot + 1}: {', '.join(words)}" + (" (played game, allowed)" if game.played else "")
        return self.push(FranchiseEdit("game", label, {"row": row, "slot": slot, "fields": changes, "allow_played": allow}))

    def swap_home_away(self, row: int, slot: int) -> bool:
        if self._save is None:
            return False
        try:
            game = self._save.game(row, slot)
        except fs.FranchiseSaveError as exc:
            self._set_status(f"Refused: {exc}")
            return False
        return self.edit_game(row, slot, home=game.away, away=game.home)

    def _apply_game_clicked(self) -> None:
        game = self._selected_game()
        if game is None:
            return
        self.edit_game(game.row, game.slot, home=int(self.home_combo.currentData()), away=int(self.away_combo.currentData()),
                       month=self.month_spin.value(), day=self.day_spin.value(),
                       hour=self.hour_spin.value(), minute=self.minute_spin.value())

    def _swap_clicked(self) -> None:
        game = self._selected_game()
        if game is not None:
            self.swap_home_away(game.row, game.slot)

    # ------------------------------------------------------------------ coach edits
    def select_coach(self, coach_index: int) -> bool:
        if coach_index in self._coach_rows:
            self.coach_list.setCurrentRow(self._coach_rows.index(coach_index))
            return True
        return False

    def set_coach_value(self, coach_index: int, name: str, value: int) -> bool:
        if self._save is None:
            return False
        coach = next((c for c in self._save.coaches() if c.index == coach_index), None)
        if coach is None:
            self._set_status(f"Refused: no coach {coach_index}")
            return False
        before = coach.fields.get(name, coach.ratings.get(name, coach.tendencies.get(name)))
        if before == int(value):
            return False
        caption = dict(COACH_STATS).get(name, caption_for(name))
        return self.push(FranchiseEdit("coach", f"{coach.name or f'coach {coach.index}'}: {caption} {before} → {int(value)}",
                                       {"coach": coach_index, "name": name, "value": int(value)}))

    def _coach_value_changed(self, name: str, value: int) -> None:
        if self._quiet:
            return
        coach = self._current_coach()
        if coach is not None:
            self.set_coach_value(coach.index, name, int(value))

    # ------------------------------------------------------------------ injured reserve
    def place_on_ir(self, team: int, player_index: int) -> bool:
        """Finn's *Place on IR* for one rostered player; his refusals first, then the core's."""

        if self._save is None or self._document is None:
            return False
        if not self.sync_from_roster():
            return False
        player = self._players.get(player_index)
        if player is not None:
            if self._document.is_draft_class(player):
                self._set_status(f"Refused: {rr.MSG_DRAFT_CLASS}")
                return False
            if self._document.is_free_agent(player) and not player.teams:
                self._set_status(f"Refused: {rr.MSG_FREE_AGENT_IR}")
                return False
        name = self._save.player_name(player_index) if player is None else player.display
        return self.push(FranchiseEdit("ir_place", f"{self._team_short(team)}: {name} (#{player_index}) placed on injured reserve",
                                       {"team": team, "player": player_index}))

    def activate_from_ir(self, team: int, player_index: int) -> bool:
        if self._save is None:
            return False
        if not self.sync_from_roster():
            return False
        name = self._save.player_name(player_index) or f"#{player_index}"
        return self.push(FranchiseEdit("ir_activate", f"{self._team_short(team)}: {name} (#{player_index}) activated from "
                                                      f"injured reserve (unwitnessed in game)",
                                       {"team": team, "player": player_index}))

    def ir_candidates(self, team: int) -> list[tuple[int, str]]:
        """The team's rostered players right now (roster edits and earlier IR moves included)."""

        if self._save is None:
            return []
        self.sync_from_roster()
        return [(index, self._player_text(index)) for index in self._save.team_player_indices(team)]

    def _place_ir_clicked(self) -> None:
        if self._save is None:
            return
        team = self._ir_team()
        dialog = IrPickerDialog(self._team_label(team), self.ir_candidates(team), self)
        if dialog.exec_() == QDialog.Accepted:
            chosen = dialog.chosen()
            if chosen is not None:
                self.place_on_ir(team, chosen)

    def _activate_ir_clicked(self) -> None:
        if self._save is None:
            return
        team = self._ir_team()
        row = self.ir_table.currentRow()
        item = self.ir_table.item(row, 2) if row >= 0 else None
        if item is None or not item.text():
            self._set_status("Select a filled injured-reserve slot first.")
            return
        self.activate_from_ir(team, int(item.text()))

    # ------------------------------------------------------------------ chrome
    def _set_status(self, text: str) -> None:
        self.status_label.setText(text)

    @property
    def last_error(self) -> str:
        return self._last_error


__all__ = ["COACH_STATS", "EDITABLE_HERE", "FranchiseEdit", "FranchisePanel", "IrPickerDialog", "money"]
