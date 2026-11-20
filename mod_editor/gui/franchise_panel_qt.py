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
statistics, formation-mix (Finn's "Back Field") and rating pages, and *Place on IR*.  Unwitnessed in game except where the core
module says otherwise (the year rule, the IR move); the activation is the unlabelled inverse.
"""

from __future__ import annotations

from mod_editor.gui.ux_text import Details, plain_error

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Sequence

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
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
from mod_editor.core import nfl2k5_coach_file as cf              # b81 R2: Finn's coach file (G5)
from mod_editor.core import nfl2k5_injured_reserve_save as irs   # b780-uxfix: modern injured reserve (IR1)
from mod_editor.core import nfl2k5_team_stats as ts               # b81 R41: Finn's Stats tab and Boxscore
from mod_editor.gui.franchise_stats_qt import BoxScoreDialog, TeamStatsPage

# the coach numbers Finn's Statistics group edits, in his order, then the two ids and the playcalling split
COACH_STATS: tuple[tuple[str, str], ...] = (
    ("wins", "Wins"), ("losses", "Losses"), ("ties", "Ties"),
    ("seasons_with_team", "Seasons with team"), ("total_seasons", "Total seasons"),
    ("winning_seasons", "Winning seasons"), ("super_bowls", "Super Bowls (roster)"),
    ("super_bowl_wins", "Super Bowl wins"), ("super_bowl_losses", "Super Bowl losses"),
    ("playoff_wins", "Playoff wins"), ("playoff_losses", "Playoff losses"),
    ("season_wins", "This season: wins"), ("season_losses", "This season: losses"),
    ("season_ties", "This season: ties"),
    ("photo", "Photo id"), ("body", "Body"), ("playcalling_run", "Playcalling: run %"),
)
# b780 Q35: +0x32 holds the Super Bowl appearances the roster gives a coach. With the coach Super Bowl fix (on in every
# preset) a franchise never changes it; Super Bowls played in the franchise count in Super Bowl wins and losses.
COACH_STAT_TIPS = {
    "super_bowls": ("The Super Bowl appearances the roster gives this coach. With the coach Super Bowl fix (on in every "
                    "preset) it does not change during a franchise: Super Bowls played in the franchise count in Super "
                    "Bowl wins and Super Bowl losses. Without the fix, retail adds one for every winning season."),
}
# The ten formation bytes are two five-class distributions (see nfl2k5_franchise_save.COACH_FORMATION_CLASSES): the formation
# a coach's CPU RUN calls come from, then the same five classes for his PASS calls.
FORMATION_WORDS = {"gun": "shotgun / pistol / empty", "split_backs": "split backs", "i_form": "I form",
                   "one_back": "one back", "no_back": "no back"}
assert tuple(FORMATION_WORDS) == fs.COACH_FORMATION_CLASSES
CALL_WORDS = {"run": "Run calls", "pass": "Pass calls"}
TENDENCY_CAPTIONS = {f"{call}_{formation}": f"{words}: {formation_words}"
                     for call, words in CALL_WORDS.items() for formation, formation_words in FORMATION_WORDS.items()}
assert tuple(TENDENCY_CAPTIONS) == fs.COACH_TENDENCIES
_CAPTIONS = {
    "qb": "QB", "rb": "RB", "te": "TE", "wr": "WR", "ol": "OL", "dl": "DL", "lb": "LB", "db": "DB",
    "rush_for": "Rush For", "pass_for": "Pass For", **TENDENCY_CAPTIONS,
}
CHECKS_RANGE_LINES = 60                    # the Checks page lists this many changed byte ranges, then says how many more
YEAR_MIN, YEAR_MAX = fs.DISPLAY_YEAR_BASE, fs.DISPLAY_YEAR_BASE + fs.FRANCHISE_MAX_YEAR_INDEX
CAP_MAX_MILLIONS = 0x7FFFFFFF / 1000
GRID_ROW_TITLES = tuple(fs.ROW_NAMES.get(row, f"week {row + 1}").title() for row in range(fs.GRID_ROWS))
EDITABLE_HERE = (
    ("Season year", "EXPERIMENTAL / UNWITNESSED", "base year + index; editable indices 0..127"),
    ("User-controlled teams", "PROVED", "FUN_000c4d70 reads the flags; Finn 0x913CC"),
    ("Salary cap", "PROVED", "DAT_00e3c278 in $1000 units; Finn 0x9ACCC"),
    ("Schedule cells", "PROVED", "the 22 x 17 grid; a played cell is refused unless you allow it; "
                                 "swapping a played game's sides swaps its score halves too"),
    ("Box score (b81 R41)", "PROVED",
     "home Q1-Q4, OT then away at season block +0x107A; the standings getters 0xC7720/0xC7750/0xC7780 count W-L-T "
     "from these bytes; optional matching change to points scored/allowed (+0x1D8/+0x1DA); unwitnessed in game"),
    ("Team statistics (b81 R41)", "READ-ONLY", "31 season words at team +0x1AA..+0x1E8, Finn's columns"),
    ("Coach record", "PROVED", "Finn's map, career numbers re-checked on real coaches; a name changes only through Fire and hire"),
    ("Coach file export and import (b81 R2)", "HYPOTHESIS",
     "Finn's .Coaches INI (48 keys a club, RE receipt coach-io.json) matched to each club's head coach; names go through "
     "the Fire and hire text writer; unwitnessed in game"),
    ("Clear cap penalty (b81 R2)", "PROVED",
     "team +0x19C..+0x1A9 = seven u16 dead-cap amounts by season (game 0x13ED30 / 0x13ED70); Finn zeroes only the first "
     "two; all seven are cleared; only user-controlled clubs accrue it; no non-zero example was in the fixtures"),
    ("Head coach moves: swap, fire and hire", "HYPOTHESIS",
     "two club pointers (+0x14C) and the coach text; the game's Create Team routine makes the same pointer change, unwitnessed in game"),
    ("Injured reserve: place", "PROVED", "Finn's 17-byte move reproduced byte for byte"),
    ("Injured reserve: activate", "HYPOTHESIS", "the inverse move, unwitnessed in game"),
)


def money(units: int) -> str:
    """$1000 units the way the game prints them: 88,113 -> $88.1M."""

    return f"${units / 1000:.1f}M"


def dead_cap_text(units: int) -> str:
    """A dead-cap amount ($1000 units) the way Finn prints a cap penalty: under a million in thousands, else millions."""

    return f"${units}k" if units < 1000 else money(units)


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
            if "index" in a:
                save.set_year_field(int(a["index"]))
            else:
                save.set_display_year(int(a["year"]))
        elif self.kind == "cap":
            save.set_salary_cap(int(a["value"]))
        elif self.kind == "control":
            save.set_user_control(int(a["team"]), bool(a["controlled"]))
        elif self.kind == "game":
            save.set_game(int(a["row"]), int(a["slot"]), allow_played=bool(a.get("allow_played", False)),
                          **{k: int(v) for k, v in dict(a["fields"]).items()})
        elif self.kind == "game_add":           # b81 R8: Finn's Add Game, Remove Game and Clear Week
            save.add_game(int(a["row"]), allow_played=bool(a.get("allow_played", False)),
                          **{k: int(v) for k, v in dict(a["fields"]).items()})
        elif self.kind == "game_remove":
            save.remove_game(int(a["row"]), int(a["slot"]), allow_played=bool(a.get("allow_played", False)))
        elif self.kind == "week_clear":
            save.clear_week(int(a["row"]), allow_played=bool(a.get("allow_played", False)))
        elif self.kind == "box_score":           # b81 R41: Finn's Boxscore
            ts.set_box_score(save, int(a["row"]), int(a["slot"]), [int(v) for v in a["home"]],
                             [int(v) for v in a["away"]], season_points=bool(a.get("season_points", True)))
        elif self.kind == "game_swap_played":    # b81 R41: a played game's sides swap with their scores
            ts.swap_played_sides(save, int(a["row"]), int(a["slot"]))
        elif self.kind == "team_option":         # b81 R13: Finn's Options tab, one or several settings of one club
            changes = dict(a["changes"]) if "changes" in a else {str(a["option"]): a["value"]}
            for option, value in changes.items():
                save.set_team_option(int(a["team"]), str(option), int(value))
        elif self.kind == "coaches_import":      # b81 R2: Finn's Import Coaches, one edit for the whole file
            cf.import_coaches(save, str(a["text"]))
        elif self.kind == "dead_cap_clear":      # b81 R2: Finn's Clear Cap Penalty, all seven seasons
            ts.clear_dead_cap(save, int(a["team"]))
        elif self.kind == "coach":
            save.set_coach_field(int(a["coach"]), str(a["name"]), int(a["value"]))
        elif self.kind == "coach_swap":
            save.swap_head_coaches(int(a["a"]), int(a["b"]), restart=bool(a.get("restart", True)),
                                   announcer_generic=bool(a.get("announcer", True)))
        elif self.kind == "coach_hire":
            save.hire_head_coach(int(a["team"]), int(a["coach"]), restart=bool(a.get("restart", True)),
                                 announcer_generic=bool(a.get("announcer", True)))
        elif self.kind == "coach_replace":
            save.replace_head_coach(int(a["team"]), str(a["first"]), str(a["last"]), [str(x) for x in a.get("bio", ())])
        elif self.kind == "ir_place":
            if irs.read_state(save).extension:   # b780-uxfix: modern IR keeps its own rules and games-missed clock
                _replace_bytes(save, irs.place(save, int(a["team"]), int(a["player"])))
            else:
                # b780 hunt5: the game's removal rule keeps the holder and returners on their players (never Finn's bytes)
                save.place_on_injured_reserve(int(a["team"]), int(a["player"]), finn_roles=False)
        elif self.kind == "promote_reserve":
            save.promote_reserve(int(a["team"]), int(a["player"]))
        elif self.kind == "demote_active":
            save.demote_active(int(a["team"]), int(a["player"]))
        elif self.kind == "ir_activate":
            if irs.read_state(save).extension:
                _replace_bytes(save, irs.activate(save, int(a["team"]), int(a["player"])))
            else:
                save.activate_from_injured_reserve(int(a["team"]), int(a["player"]))
        else:
            raise fs.FranchiseSaveError(f"unknown franchise edit {self.kind!r}")


def _replace_bytes(save: fs.FranchiseSave, payload: bytes) -> None:
    """Take the bytes a core writer returned (same length) into the live save, dropping its parsed roster."""
    if len(payload) != len(save.buffer):
        raise fs.FranchiseSaveError("the injured reserve edit changed the save length")
    save.buffer[:] = payload
    save._roster = None


#: b780-uxfix: the IR table: the three old columns, then what modern injured reserve adds.
IR_COLUMNS = ("Slot", "Player", "Player index", "Games missed", "Season-ending", "Can return")
IR_LEGACY_NOTE = ("This save has 5 injured reserve slots a club (an older build wrote it). Modern injured reserve, "
                  "with 20 slots, the 4-game minimum and 8 returns a season, starts when the save is loaded and "
                  "saved once in a build with modern injured reserve.")


# --------------------------------------------------------------------------------------------- dialogs
class IrPickerDialog(QDialog):
    """Finn's *Place on IR*: pick one of the team's rostered players."""

    def __init__(self, team_label: str, rows: Sequence[tuple[int, str]], parent: QWidget | None = None,
                 *, selected: int | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Place on injured reserve: {team_label}")
        layout = QVBoxLayout(self)
        hint = QLabel("Choose the player. He leaves the team's list the way Finn's editor does it, and the holder, "
                      "kicker and returner choices stay with the same players, as the game's own roster moves keep them; "
                      "the game recomputes the team salary. Not yet tested in-game.")
        hint.setWordWrap(True)
        hint.setToolTip("His team's pointer list is compacted and its count drops by one, Finn's move. A role he held "
                        "is cleared, the way the game clears it when a player leaves a team.")
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
        if selected is not None:            # b81: the Rosters grid's right-click Place on IR… arrives with him chosen
            for row in range(self.list.count()):
                if self.list.item(row).data(Qt.UserRole) == int(selected):
                    self.list.setCurrentRow(row)
                    break

    def chosen(self) -> int | None:
        item = self.list.currentItem()
        return None if item is None else int(item.data(Qt.UserRole))


class ClubPickerDialog(QDialog):
    """Pick one club for a head coach move, with the new-job options and a plain sentence for what will happen."""

    def __init__(self, title: str, intro: str, rows: Sequence[tuple[int, str]], describe: Callable[[int], str],
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self._describe = describe
        layout = QVBoxLayout(self)
        hint = QLabel(intro)
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.list = QListWidget()
        self.list.setAccessibleName("Clubs")
        for team, text in rows:
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, team)
            self.list.addItem(item)
        self.list.currentRowChanged.connect(self._row_changed)
        self.list.itemDoubleClicked.connect(lambda _item: self.accept())
        layout.addWidget(self.list, 1)
        self.summary = QLabel("Choose a club.")
        self.summary.setWordWrap(True)
        self.summary.setAccessibleName("What will happen")
        layout.addWidget(self.summary)
        self.restart_check = QCheckBox("Start the new job at year 1 (career totals, ratings and play calling stay)")
        self.restart_check.setChecked(True)
        self.restart_check.setToolTip("Seasons with the club and this season's record go back to zero. "
                                      "Untick to keep them as they are.")
        self.announcer_check = QCheckBox('Announcers say "the head coach" instead of a name')
        self.announcer_check.setChecked(True)
        self.announcer_check.setToolTip("The announcer picks a coach's name from the club, so after a move it would say "
                                        "the old coach's name. This marks the record 'no recorded name'. "
                                        "Not yet tested in the game.")
        layout.addWidget(self.restart_check)
        layout.addWidget(self.announcer_check)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.ok_button = buttons.button(QDialogButtonBox.Ok)
        self.ok_button.setEnabled(False)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.resize(460, 560)

    def _row_changed(self, row: int) -> None:
        team = self.chosen()
        self.ok_button.setEnabled(team is not None)
        self.summary.setText(self._describe(team) if team is not None else "Choose a club.")

    def chosen(self) -> int | None:
        item = self.list.currentItem()
        return None if item is None else int(item.data(Qt.UserRole))

    def options(self) -> dict[str, bool]:
        return {"restart": self.restart_check.isChecked(), "announcer": self.announcer_check.isChecked()}


class FireHireDialog(QDialog):
    """Fire a club's head coach and hire a coach already in the save, or a new person who takes his record."""

    def __init__(self, team_label: str, coach_name: str, on_file: Sequence[tuple[int, str]], name_problem: str,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Fire and hire: {team_label}")
        layout = QVBoxLayout(self)
        intro = QLabel(f"{coach_name} is fired as head coach of {team_label}. Who takes over?")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        self.file_radio = QRadioButton("A coach already in this save")
        self.file_combo = QComboBox()
        self.file_combo.setAccessibleName("Coach already in this save")
        for index, text in on_file:
            self.file_combo.addItem(text, index)
        self.file_note = QLabel("")
        self.file_note.setWordWrap(True)
        layout.addWidget(self.file_radio)
        layout.addWidget(self.file_combo)
        layout.addWidget(self.file_note)
        self.new_radio = QRadioButton("A new coach")
        layout.addWidget(self.new_radio)
        names = QHBoxLayout()
        self.first_field = QLineEdit()
        self.first_field.setPlaceholderText("First name")
        self.first_field.setAccessibleName("New coach first name")
        self.first_field.setMaxLength(fs.COACH_NAME_MAX)
        self.last_field = QLineEdit()
        self.last_field.setPlaceholderText("Last name")
        self.last_field.setAccessibleName("New coach last name")
        self.last_field.setMaxLength(fs.COACH_NAME_MAX)
        names.addWidget(self.first_field)
        names.addWidget(self.last_field)
        layout.addLayout(names)
        self.bio_fields: list[QLineEdit] = []
        for number in range(1, 4):
            field = QLineEdit()
            field.setPlaceholderText(f"Biography line {number} (optional)")
            field.setAccessibleName(f"New coach biography line {number}")
            field.setMaxLength(fs.COACH_BIO_MAX)
            self.bio_fields.append(field)
            layout.addWidget(field)
        self.new_note = QLabel(
            f"He takes over {coach_name}'s record: the ratings, play calling and sideline body stay, the name and "
            f"biography are new, his career starts at zero and he has no picture. {coach_name} is removed from this save.")
        self.new_note.setWordWrap(True)
        layout.addWidget(self.new_note)
        self.restart_check = QCheckBox("Start the hired coach's time at year 1 (career totals, ratings and play calling stay)")
        self.restart_check.setChecked(True)
        self.announcer_check = QCheckBox('Announcers say "the head coach" instead of a name')
        self.announcer_check.setChecked(True)
        layout.addWidget(self.restart_check)
        layout.addWidget(self.announcer_check)
        self._name_problem = name_problem
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.ok_button = buttons.button(QDialogButtonBox.Ok)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.file_radio.toggled.connect(self._mode_changed)
        self.new_radio.toggled.connect(self._mode_changed)
        self.first_field.textChanged.connect(self._mode_changed)
        self.last_field.textChanged.connect(self._mode_changed)
        has_file = bool(on_file)
        self.file_radio.setEnabled(has_file)
        self.file_note.setText(f"{coach_name} stays on file and can be hired again." if has_file else
                               "No unemployed coaches are on file yet. Fire a coach and hire a new one, or swap two clubs.")
        if name_problem:
            self.new_radio.setEnabled(False)
            self.new_note.setText(name_problem)
        (self.file_radio if has_file else self.new_radio).setChecked(True)
        self._mode_changed()
        self.resize(480, 520)

    def _mode_changed(self, *_args: object) -> None:
        existing = self.file_radio.isChecked()
        self.file_combo.setEnabled(existing and self.file_radio.isEnabled())
        for widget in (self.first_field, self.last_field, *self.bio_fields):
            widget.setEnabled(not existing and self.new_radio.isEnabled())
        self.restart_check.setEnabled(existing)
        self.announcer_check.setEnabled(existing)
        if existing and self.file_radio.isEnabled():
            ready = self.file_combo.currentData() is not None
        else:
            ready = (self.new_radio.isEnabled() and self.new_radio.isChecked()
                     and bool(self.first_field.text().strip()) and bool(self.last_field.text().strip()))
        self.ok_button.setEnabled(ready)

    def choice(self) -> dict[str, Any] | None:
        if self.file_radio.isChecked() and self.file_radio.isEnabled():
            data = self.file_combo.currentData()
            if data is None:
                return None
            return {"kind": "file", "coach": int(data), "restart": self.restart_check.isChecked(),
                    "announcer": self.announcer_check.isChecked()}
        if self.new_radio.isChecked() and self.new_radio.isEnabled():
            return {"kind": "new", "first": self.first_field.text(), "last": self.last_field.text(),
                    "bio": [field.text() for field in self.bio_fields]}
        return None


# --------------------------------------------------------------------------------------------- the page
class CoachImportDialog(QDialog):
    """What a Finn coach file would change, one line a field (club, coach, field, old -> new), before anything is applied."""

    def __init__(self, plan: cf.ImportPlan, file_name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.plan = plan
        self.setWindowTitle("Import coaches")
        self.resize(760, 520)
        layout = QVBoxLayout(self)
        self.summary_label = QLabel(f"{file_name}: {plan.sections} club section{'s' if plan.sections != 1 else ''}, "
                                    f"{plan.matched} matched to a head coach. {plan.summary()}")
        self.summary_label.setWordWrap(True)
        self.summary_label.setAccessibleName("Import summary")
        layout.addWidget(self.summary_label)
        self.table = QTableWidget(len(plan.changes), 5)
        self.table.setHorizontalHeaderLabels(["Club", "Coach", "Field", "Now", "Becomes"])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.setAccessibleName("Coach changes")
        for row, change in enumerate(plan.changes):
            caption = ("First name" if change.field == "first" else "Last name" if change.field == "last"
                       else dict(COACH_STATS).get(change.field, caption_for(change.field)))
            cells = [change.club, change.coach_name, f"{caption} ({change.key})", str(change.old), str(change.new)]
            for column, text in enumerate(cells):
                self.table.setItem(row, column, QTableWidgetItem(text))
        self.table.resizeColumnsToContents()
        layout.addWidget(self.table, 1)
        notes = list(plan.refusals)
        if plan.name_changes and plan.name_problem:
            notes.append(f"Names cannot be written in this save ({plan.name_problem}); the numbers apply and the "
                         f"{len(plan.name_changes)} name change{'s' if len(plan.name_changes) != 1 else ''} are skipped.")
        notes += plan.skipped
        self.notes = QPlainTextEdit("\n".join(notes))
        self.notes.setReadOnly(True)
        self.notes.setAccessibleName("Import notes")
        self.notes.setVisible(bool(notes))
        self.notes.setMaximumHeight(110)
        layout.addWidget(self.notes)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        ok = self.buttons.button(QDialogButtonBox.Ok)
        ok.setText("Apply")
        ok.setEnabled(plan.ok and bool(plan.changes))
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def rows(self) -> list[list[str]]:
        return [[self.table.item(r, c).text() for c in range(self.table.columnCount())] for r in range(self.table.rowCount())]


class FranchisePanel(QWidget):
    """The Franchise page: Overview, Schedule, Coaches, Injured Reserve, Checks."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.shared_roster_panel = None
        self._container: rr.SaveContainer | None = None
        self._document: rr.RosterDocument | None = None
        self._base = b""
        self._save: fs.FranchiseSave | None = None
        # b81 R5: "franchise", or "roster" for a roster save, where only the Coaches tab shows (Finn edits coaches in any
        # save); the same page, journal and writers serve both
        self._mode = ""
        self._edits: list[FranchiseEdit] = []
        self._cursor = 0
        self._quiet = False
        self._base_year = fs.DISPLAY_YEAR_BASE
        self._players: dict[int, rr.Player] = {}
        self._coach_rows: list[int] = []
        self._coach_cards: dict[str, Any] = {}
        self._coach_sum_labels: dict[str, QLabel] = {}
        self._coach_spins: dict[str, QSpinBox] = {}
        self._host: QTabWidget | None = None
        self._host_index = -1
        self._checks_stale = True
        self._last_error = ""
        self.last_import_receipt: dict[str, Any] = {}
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
        self._host.setTabText(self._host_index, "Coaches" if self._mode == "roster" else "Franchise")
        self._host.setTabToolTip(self._host_index, "The coaches of this roster save: their numbers, ratings, play calling "
                                                   "and head-coach moves." if self._mode == "roster" else "")
        if not visible and self._host.currentIndex() == self._host_index:
            self._host.setCurrentIndex(0)
        self._host.setTabVisible(self._host_index, visible)
        # the bar stays whenever another page besides Roster exists (the disc-only ESPN Anniversary tab)
        others = any(self._host.isTabVisible(i) for i in range(self._host.count()) if i not in (0, self._host_index))
        self._host.tabBar().setVisible(visible or others)

    @property
    def active(self) -> bool:
        """A FRANCHISE save is loaded (a roster save's coaches use this page too; see ``coaches_only``)."""

        return self._save is not None and self._mode == "franchise"

    @property
    def coaches_only(self) -> bool:
        """b81 R5: a roster save is loaded and this page shows only its Coaches tab."""

        return self._save is not None and self._mode == "roster"

    def _new_save(self, payload: bytes) -> fs.FranchiseSave:
        """A FranchiseSave over ``payload`` in this page's mode (a roster save has no franchise season)."""

        if self._mode == "roster":
            return fs.FranchiseSave.roster_save(payload, container=self._container, base_year=self._base_year)
        return fs.FranchiseSave(payload, container=self._container)

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

        self.upgrade_button = QPushButton("Upgrade franchise save to the current build")
        self.upgrade_button.setToolTip("Preview an older SOFTDRINK 2026 franchise upgrade and export a new signed copy.")
        self.upgrade_button.clicked.connect(self._upgrade_clicked)
        layout.addWidget(self.upgrade_button)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_overview(), "Overview")
        self.tabs.addTab(self._build_schedule(), "Schedule")
        self.coaches_page = self._build_coaches()
        self.tabs.addTab(self.coaches_page, "Coaches")
        self._ir_tab_index = self.tabs.addTab(self._build_injured_reserve(), "Injured Reserve")
        self.tabs.addTab(self._build_checks(), "Checks")
        # b81 R41: Finn's Stats tab, last so the older tab positions stay where they were
        self.stats_page = TeamStatsPage()
        self._stats_tab_index = self.tabs.addTab(self.stats_page, "Team Stats")
        self.tabs.setTabToolTip(self._stats_tab_index, "Each club's season numbers, the way Finn's Stats tab shows "
                                                       "them (read-only).")
        self.tabs.currentChanged.connect(self._tab_changed)
        layout.addWidget(self.tabs, 1)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

    def _build_overview(self) -> QWidget:
        page = QWidget()
        box = QVBoxLayout(page)
        form = QFormLayout()
        self.base_year_spin = QSpinBox()
        self.base_year_spin.setRange(100, 9744)
        self.base_year_spin.setValue(self._base_year)
        self.base_year_spin.setKeyboardTracking(False)
        self.base_year_spin.setToolTip("Use your build's starting year: 2004 for Retail, 2026 for a 2026 build. "
                                      "The save does not record this choice. This changes the view only.")
        self.base_year_spin.valueChanged.connect(self._base_year_changed)
        form.addRow("Build starting year", self.base_year_spin)
        year_row = QHBoxLayout()
        self.year_spin = QSpinBox()
        self.year_spin.setRange(YEAR_MIN, YEAR_MAX)
        self.year_spin.setKeyboardTracking(False)
        self.year_spin.setAccessibleName("Season year")
        self.year_spin.valueChanged.connect(self._year_changed)
        year_row.addWidget(self.year_spin)
        self.year_rule_label = QLabel("")
        self.year_rule_label.setWordWrap(True)
        year_row.addWidget(self.year_rule_label, 1)
        form.addRow("Season year", year_row)
        self.season_cap_label = QLabel()
        self.season_cap_label.setWordWrap(True)
        form.addRow(self.season_cap_label)
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
        self.salary_table = QTableWidget(0, 5)
        self.salary_table.setHorizontalHeaderLabels(["Team", "Salary", "Cap space", "Note", "Dead cap"])
        self.salary_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.salary_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.salary_table.verticalHeader().setVisible(False)
        self.salary_table.itemSelectionChanged.connect(self._refresh_dead_cap_button)
        salary_layout.addWidget(self.salary_table)
        penalty_row = QHBoxLayout()
        self.clear_cap_button = QPushButton("Clear cap penalty…")
        self.clear_cap_button.setToolTip("Zero the selected club's dead cap in every season. Only clubs a person controls "
                                         "ever pile up dead cap in the game.")
        self.clear_cap_button.clicked.connect(self._clear_cap_clicked)
        penalty_row.addWidget(self.clear_cap_button)
        self.dead_cap_label = QLabel("")
        self.dead_cap_label.setWordWrap(True)
        penalty_row.addWidget(self.dead_cap_label, 1)
        salary_layout.addLayout(penalty_row)
        lists.addWidget(salary_box, 2)
        box.addLayout(lists, 1)
        return page

    def _build_schedule(self) -> QWidget:
        page = QWidget()
        box = QVBoxLayout(page)
        top = QHBoxLayout()
        top.addWidget(QLabel("Week / round"))
        self.week_combo = QComboBox()
        self.week_combo.addItems(list(GRID_ROW_TITLES))
        self.week_combo.addItem("All postseason")
        self.week_combo.setAccessibleName("Schedule week")
        self.week_combo.currentIndexChanged.connect(lambda _i: self._refresh_schedule())
        top.addWidget(self.week_combo)
        self.week_label = QLabel("")
        top.addWidget(self.week_label, 1)
        box.addLayout(top)
        self.schedule_table = QTableWidget(0, 8)
        self.schedule_table.setHorizontalHeaderLabels(["#", "Away", "Home", "Date", "Kick-off", "Played", "Score", "Round"])
        self.schedule_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.schedule_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.schedule_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.schedule_table.verticalHeader().setVisible(False)
        self.schedule_table.itemSelectionChanged.connect(self._schedule_row_selected)
        self.schedule_table.itemDoubleClicked.connect(lambda _item: self._box_score_clicked())
        box.addWidget(self.schedule_table, 1)

        # b81 R8: Finn's Home/Away table, read-only, with what looks wrong said in words
        self.integrity_label = QLabel("")
        self.integrity_label.setWordWrap(True)
        self.integrity_label.setAccessibleName("Season check")
        box.addWidget(self.integrity_label)
        self.integrity_details = Details("Games per club (home and away)")
        self.integrity_table = QTableWidget(0, 5)
        self.integrity_table.setHorizontalHeaderLabels(["Club", "Home", "Away", "Games", "Check"])
        self.integrity_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.integrity_table.verticalHeader().setVisible(False)
        self.integrity_table.horizontalHeader().setStretchLastSection(True)
        self.integrity_table.setAccessibleName("Games per club")
        self.integrity_table.setMinimumHeight(120)
        self.schedule_table.setMinimumHeight(140)       # the open check never squeezes the week to one row
        self.integrity_details.content.addWidget(self.integrity_table)
        box.addWidget(self.integrity_details)

        editor = QGroupBox("Edit the selected game")
        grid = QGridLayout(editor)
        self.away_combo = QComboBox()
        self.away_combo.setAccessibleName("Away team")
        self.away_combo.setPlaceholderText("To be decided")
        self.home_combo = QComboBox()
        self.home_combo.setAccessibleName("Home team")
        self.home_combo.setPlaceholderText("To be decided")
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
        self.box_score_button = QPushButton("Box score…")
        self.box_score_button.setToolTip("Finn's Boxscore: both clubs' quarter scores for a played game "
                                         "(double-click a played game too).")
        self.box_score_button.clicked.connect(self._box_score_clicked)
        self.allow_played_check = QCheckBox("Allow editing played games")
        self.allow_played_check.setToolTip("A played cell carries its score and flags; the page refuses to "
                                           "change it unless you tick this")
        self.allow_played_check.toggled.connect(lambda _checked: self._update_game_notice())
        buttons.addWidget(self.apply_game_button)
        buttons.addWidget(self.swap_button)
        buttons.addWidget(self.box_score_button)
        buttons.addWidget(self.allow_played_check)
        schedule_note = QLabel("EXPERIMENTAL / UNWITNESSED")
        schedule_note.setObjectName("optionBadge")
        schedule_note.setToolTip("Schedule and box score edits write the save's grid cells; "
                                 "nobody has watched the game accept them yet.")
        buttons.addWidget(schedule_note)
        buttons.addStretch(1)
        grid.addLayout(buttons, 2, 0, 1, 4)
        week_tools = QHBoxLayout()
        self.add_game_button = QPushButton("Add game to this week")
        self.add_game_button.setToolTip("Finn's Add Game: a new game in this week with the teams, date and kick-off "
                                        "above. Regular-season weeks only; refused if either team already plays.")
        self.add_game_button.clicked.connect(self._add_game_clicked)
        self.remove_game_button = QPushButton("Remove this game")
        self.remove_game_button.setToolTip("Finn's Remove Game: the week's later games move up one place.")
        self.remove_game_button.clicked.connect(self._remove_game_clicked)
        self.clear_week_button = QPushButton("Clear this week")
        self.clear_week_button.setToolTip("Finn's Clear Week: remove every game of this week.")
        self.clear_week_button.clicked.connect(self._clear_week_clicked)
        for button in (self.add_game_button, self.remove_game_button, self.clear_week_button):
            week_tools.addWidget(button)
        week_tools.addStretch(1)
        grid.addLayout(week_tools, 3, 0, 1, 4)
        self.game_notice = QLabel("")
        self.game_notice.setWordWrap(True)
        self.game_notice.setAccessibleName("Selected game editing notice")
        grid.addWidget(self.game_notice, 4, 0, 1, 4)
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
        coach_note = QLabel("Coach edits: not yet tested in-game. Names and info lines are read-only here (pooled text); "
                            "Fire and hire gives a club a new name.")
        coach_note.setWordWrap(True)
        box.addWidget(coach_note)
        moves = QGroupBox("Staff moves")
        moves_box = QVBoxLayout(moves)
        moves_note = QLabel(
            "Swap two clubs' head coaches, fire a head coach and hire another, or hire a coach who has no club. "
            "A coach keeps his career totals, ratings and play calling; his time with the new club starts at year 1. "
            "The Studio's automatic 2026 play calling stays with each club's original coach, so it is off for a club "
            "whose head coach changed. Not yet tested in the game.")
        moves_note.setWordWrap(True)
        moves_box.addWidget(moves_note)
        moves_row = QHBoxLayout()
        self.coach_swap_button = QPushButton("Swap with another club…")
        self.coach_swap_button.setToolTip("Exchange this head coach with another club's head coach. Nobody loses a job.")
        self.coach_swap_button.clicked.connect(self._coach_swap_clicked)
        self.coach_fire_button = QPushButton("Fire and hire…")
        self.coach_fire_button.setToolTip("Fire this head coach and hire a coach already in the save, or a new person.")
        self.coach_fire_button.clicked.connect(self._coach_fire_clicked)
        self.coach_hire_button = QPushButton("Hire for a club…")
        self.coach_hire_button.setToolTip("Give this coach, who has no club, a club's head coach job. "
                                          "The club's current head coach is fired and stays on file.")
        self.coach_hire_button.clicked.connect(self._coach_hire_clicked)
        for button in (self.coach_swap_button, self.coach_fire_button, self.coach_hire_button):
            moves_row.addWidget(button)
        moves_row.addStretch(1)
        moves_box.addLayout(moves_row)
        self.coach_move_label = QLabel("")
        self.coach_move_label.setWordWrap(True)
        self.coach_move_label.setAccessibleName("Staff moves note")
        moves_box.addWidget(self.coach_move_label)
        box.addWidget(moves)
        backup = QGroupBox("Backup and restore (Finn's coach file)")
        backup_box = QVBoxLayout(backup)
        backup_note = QLabel(
            "Export every club's head coach to a Finn .Coaches file, or import one. A section is matched to a club by its "
            "nickname and goes to that club's head coach now, even after coaches have moved. Missing sections and keys "
            "change nothing; you see every change before it is applied, and Undo takes it all back.")
        backup_note.setWordWrap(True)
        backup_box.addWidget(backup_note)
        backup_row = QHBoxLayout()
        self.coach_export_button = QPushButton("Export coaches…")
        self.coach_export_button.setToolTip("Write every club's head coach to a .Coaches file, in Flying Finn's format.")
        self.coach_export_button.clicked.connect(self._export_coaches_clicked)
        self.coach_import_button = QPushButton("Import coaches…")
        self.coach_import_button.setToolTip("Read a .Coaches or .2k5Coaches file and show what it would change first.")
        self.coach_import_button.clicked.connect(self._import_coaches_clicked)
        backup_row.addWidget(self.coach_export_button)
        backup_row.addWidget(self.coach_import_button)
        backup_row.addStretch(1)
        backup_box.addLayout(backup_row)
        box.addWidget(backup)
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
            label = QLabel(caption)
            if name in COACH_STAT_TIPS:   # b780 Q35: say what the number is and is not
                label.setToolTip(COACH_STAT_TIPS[name])
                spin.setToolTip(COACH_STAT_TIPS[name])
            stats_grid.addWidget(label, row, column * 2)
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

        for call, words in CALL_WORDS.items():
            group = QGroupBox(f"{words} by formation (share of his {call} calls, %)")
            group.setToolTip(f"Where his CPU {call} calls come from: five formation types, each a share of all his {call} "
                             "calls. The five numbers are one distribution and add up to 100 in every coach the game ships.")
            grid = QGridLayout(group)
            for position, formation in enumerate(fs.COACH_FORMATION_CLASSES):
                name = f"{call}_{formation}"
                card = AttributeCard(name, caption_for(name), 0, 100)
                card.changed.connect(self._coach_value_changed)
                self._coach_cards[name] = card
                row, column = divmod(position, 3)
                grid.addWidget(card, row, column)
            total = QLabel("")
            total.setWordWrap(True)
            total.setAccessibleName(f"{words} formation total")
            self._coach_sum_labels[call] = total
            grid.addWidget(total, 2, 0, 1, 3)
            box.addWidget(group)
        box.addStretch(1)
        area.setWidget(host)
        page.addWidget(area)
        page.setStretchFactor(0, 1)
        page.setStretchFactor(1, 3)
        page.setSizes([250, 750])                 # a coach's name and club fit in the list
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
                                           "list and the slot is cleared. Nobody has watched the game accept it yet. "
                                           "This is a return from IR, not Finn's Heal Player: it does not change "
                                           "an injury.")
        self.activate_ir_button.clicked.connect(self._activate_ir_clicked)
        top.addWidget(self.place_ir_button)
        top.addWidget(self.activate_ir_button)
        activate_note = QLabel("Not yet tested in-game")
        activate_note.setObjectName("optionBadge")
        activate_note.setToolTip(self.activate_ir_button.toolTip())
        top.addWidget(activate_note)
        top.addStretch(1)
        box.addLayout(top)
        self.ir_returns_label = QLabel("")   # b780-uxfix: returns used, or why this save has 5 slots
        self.ir_returns_label.setWordWrap(True)
        self.ir_returns_label.setAccessibleName("Injured reserve returns")
        box.addWidget(self.ir_returns_label)
        self.ir_table = QTableWidget(fs.IR_SLOTS, len(IR_COLUMNS))
        self.ir_table.setHorizontalHeaderLabels(list(IR_COLUMNS))
        self.ir_table.itemSelectionChanged.connect(self._ir_selection_changed)
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
        explanation = QLabel("What this save supports, what you can edit here, and your franchise changes since opening it.")
        explanation.setWordWrap(True)
        top.addWidget(explanation, 1)
        box.addLayout(top)
        self.checks_text = QPlainTextEdit()
        self.checks_text.setReadOnly(True)
        box.addWidget(self.checks_text, 1)
        return page

    # ------------------------------------------------------------------ loading
    def _upgrade_clicked(self) -> None:
        if self._container is None or not self.sync_from_roster():
            return
        if self._save.to_bytes() != self._container.savegame:
            self._set_status("Write your edits to a save copy and reload it before upgrading that saved franchise.")
            return
        from mod_editor.gui.franchise_upgrade_dialog_qt import FranchiseUpgradeDialog
        FranchiseUpgradeDialog(self._container.path, self).exec_()

    def load(self, container: rr.SaveContainer, document: rr.RosterDocument) -> bool:
        """Adopt a save; returns False (and stays hidden) unless it is a franchise save, or a roster save with coach
        records, which shows only the Coaches tab (b81 R5)."""

        self.clear()
        if fs.is_franchise_save(container.savegame):
            mode = "franchise"
        else:
            try:
                fs.FranchiseSave.roster_save(container.savegame)
            except fs.FranchiseSaveError:
                return False
            mode = "roster"
        self._mode = mode
        self._container = container
        self._document = document
        self._base = bytes(container.savegame)
        self._base_year = document.base_year
        if mode == "roster":
            self._save = fs.FranchiseSave.roster_save(self._base, container=container, source=str(container.path),
                                                      base_year=self._base_year)
        else:
            self._save = fs.FranchiseSave(self._base, container=container, source=str(container.path),
                                          base_year=self._base_year)
        self._players = {p.index: p for p in document.players if p.pool == "primary"}
        self._show_mode_tabs()
        self._populate_static()
        self._refresh_all(force_checks=mode == "franchise")
        self._set_tab_visible(True)
        self._set_status(f"Franchise save: {self._save.one_line()}" if mode == "franchise" else
                         f"{self._save.one_line()}. Coach edits are written into your signed save copy with the "
                         f"roster edits. Not yet tested in-game.")
        return True

    def _show_mode_tabs(self) -> None:
        """A roster save shows the Coaches tab alone; a franchise save shows every tab."""

        coaches = self.tabs.indexOf(self.coaches_page)
        for index in range(self.tabs.count()):
            self.tabs.setTabVisible(index, self._mode != "roster" or index == coaches)
        self.upgrade_button.setVisible(self._mode != "roster")
        self.tabs.tabBar().setVisible(self._mode != "roster")      # one page needs no tab bar
        if self._mode == "roster":
            self.tabs.setCurrentIndex(coaches)

    def clear(self) -> None:
        self._container = None
        self._document = None
        self._base = b""
        self._save = None
        self._mode = ""
        self._show_mode_tabs()
        self._edits = []
        self._cursor = 0
        self._players = {}
        self._last_error = ""
        self._set_tab_visible(False)
        self._refresh_all(force_checks=True)
        self._set_status("")

    def showEvent(self, event) -> None:  # noqa: N802 - Qt naming
        super().showEvent(event)
        if self._save is not None:
            self.sync_from_roster()

    def sync_from_roster(self) -> bool:
        """Take the roster page's edits as the base and replay the franchise edits on top of them."""

        if self._save is None or self._document is None:
            return False
        try:
            # b81 R5: a roster save's page shows only its coaches, which live in the arena bytes themselves; encoding
            # every player record first (seconds on a 4,096-player roster) would change nothing it shows
            body = (bytes(self._document.body) if self._mode == "roster" and self.shared_roster_panel is not None
                    else self._document.to_body())
        except Exception as exc:  # noqa: BLE001 - one message, the roster page's own write shows the same
            self._last_error = f"the roster edits could not be applied first: {plain_error(exc)}"
            self._set_status(f"Refused: {self._last_error}")
            return False
        if len(body) != len(self._base):
            self._last_error = "the roster arena changed size"
            self._set_status(f"Refused: {self._last_error}")
            return False
        if self.shared_roster_panel is not None:
            self._base = body
            self._save = self._fresh_save()
            self._save.original = bytes(self._container.savegame)
            if self._mode == "franchise":
                # b81 item 6: this page's view is the roster page's own document written out, so the injured reserve
                # and name readers use that document instead of parsing all 4,164 records again (0.6 s a read)
                self._save._roster = self._document
            self._last_error = ""
            self._refresh_all()
            return True
        if body != self._base:
            old_base = self._base
            self._base = body
            if not self._rebuild():
                self._base = old_base
                return False
            self._refresh_all()
            return True
        return self._rebuild()

    # ------------------------------------------------------------------ the journal
    def _fresh_save(self) -> fs.FranchiseSave:
        assert self._container is not None
        if self._mode == "roster":
            return fs.FranchiseSave.roster_save(self._base, container=self._container, source=str(self._container.path),
                                                base_year=self._base_year)
        return fs.FranchiseSave(self._base, container=self._container, source=str(self._container.path),
                                base_year=self._base_year)

    def _rebuild(self) -> bool:
        """Replay on a private candidate. A failed ownership edit stays in the journal."""
        save = self._fresh_save()
        try:
            for edit in self._edits[:self._cursor]:
                edit.apply(save)
            # the roster codec is consulted only when the journal touched roster state (beta-63.1)
            from mod_editor.core.nfl2k5_practice_squad import validate_save_edit
            validate_save_edit(self._base, save.to_bytes())
        except ValueError as exc:
            self._last_error = f"Franchise journal replay refused: {exc}"
            self._set_status(self._last_error)
            return False
        self._last_error = ""
        self._save = save
        return True

    def push(self, edit: FranchiseEdit) -> bool:
        """Apply one edit to the live save and journal it; a refusal restores the live save and says why."""

        if self._save is None:
            return False
        if self.shared_roster_panel is not None:
            return self.shared_roster_panel._franchise_edit(edit)
        if not self.sync_from_roster():
            return False
        before = self._save.to_bytes()
        candidate = self._new_save(before)
        candidate.original = self._save.original
        try:
            edit.apply(candidate)
            from mod_editor.core.nfl2k5_practice_squad import validate_save_edit
            validate_save_edit(before, candidate.to_bytes())
        except ValueError as exc:
            self._last_error = str(exc)
            self._refresh_all()
            self._set_status(f"Refused: {exc}")
            return False
        self._save = candidate
        del self._edits[self._cursor:]
        self._edits.append(edit)
        self._cursor += 1
        self._checks_stale = True
        self._refresh_all()
        self._set_status(edit.label)
        return True

    def undo(self) -> str:
        if self.shared_roster_panel is not None:
            return self.shared_roster_panel.undo()
        if self._cursor == 0:
            return ""
        self._cursor -= 1
        label = self._edits[self._cursor].label
        if not self._rebuild():
            self._cursor += 1
            return ""
        self._checks_stale = True
        self._refresh_all()
        self._set_status(f"Undid: {label}")
        return label

    def redo(self) -> str:
        if self.shared_roster_panel is not None:
            return self.shared_roster_panel.redo()
        if self._cursor >= len(self._edits) or self._save is None:
            return ""
        if not self.sync_from_roster():
            return ""
        edit = self._edits[self._cursor]
        before = self._save.to_bytes()
        candidate = self._new_save(before)
        candidate.original = self._save.original
        try:
            edit.apply(candidate)
            from mod_editor.core.nfl2k5_practice_squad import validate_save_edit
            validate_save_edit(before, candidate.to_bytes())
        except ValueError as exc:
            self._refresh_all()
            self._set_status(f"Could not redo {edit.label}: {exc}")
            return ""
        self._save = candidate
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
        if self._mode == "roster":                  # b81 R5: a roster save has coaches and nothing seasonal
            self._fill_coach_list(select=None, first_row=True)
            return
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
            self._fill_coach_list(select=None, first_row=True)
            for row in range(fs.GRID_ROWS):
                self.week_combo.setItemText(row, self._save.schedule_row_name(row).title())
            self.allow_played_check.setChecked(False)
            header = self._save.header
            if header.stage == 9 or (header.stage not in (7, 8) and
                                     self._save.games(rows=range(self._save.regular_season_weeks, fs.GRID_ROWS))):
                self.week_combo.setCurrentIndex(fs.GRID_ROWS)  # every saved postseason round
            else:
                self.week_combo.setCurrentIndex(max(0, min(header.week, fs.GRID_ROWS - 1))
                                                if header.stage in (7, 8) else 0)
        finally:
            self._quiet = False

    # ------------------------------------------------------------------ refresh
    def _refresh_all(self, *, force_checks: bool = False) -> None:
        if self._mode == "roster":
            self._refresh_header()
            self._fill_coach_list()
            self._refresh_coach()
            return
        self._refresh_header()
        self._refresh_overview()
        self._refresh_schedule()
        self._fill_coach_list()
        self._refresh_coach()
        self._refresh_injured_reserve()
        self.stats_page.refresh(self._save if self._mode == "franchise" else None, self._team_label)
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
        kind = "coach" if self._mode == "roster" else "franchise"
        self.dirty_label.setText(f"● {count} {kind} edit{'s' if count != 1 else ''} (not yet written)" if count else "")
        self.undo_button.setEnabled(loaded and self._cursor > 0)
        self.redo_button.setEnabled(loaded and self._cursor < len(self._edits))
        if self.shared_roster_panel is not None:
            self.undo_button.setEnabled(loaded and self.shared_roster_panel.undo_stack.can_undo())
            self.redo_button.setEnabled(loaded and self.shared_roster_panel.undo_stack.can_redo())
        self.undo_button.setToolTip(f"Undo: {self._edits[self._cursor - 1].label}" if self._cursor else "")
        self.redo_button.setToolTip(f"Redo: {self._edits[self._cursor].label}" if self._cursor < len(self._edits) else "")

    def _refresh_overview(self) -> None:
        self._quiet = True
        try:
            if self._save is None:
                self.year_spin.setValue(YEAR_MIN)
                self.year_rule_label.setText("")
                self.season_cap_label.clear()
                self.stage_label.setText("")
                self.cap_spin.setValue(0.001)
                self.cap_raw_label.setText("")
                self.salary_table.setRowCount(0)
                self._refresh_dead_cap_button()
                return
            header = self._save.header
            self.base_year_spin.setValue(self._base_year)
            # Preserve an out-of-range terminal/foreign index visibly on load.
            # Disabling edits avoids QSpinBox silently clamping it to index 127.
            self.year_spin.setRange(self._base_year,
                                    self._base_year + max(fs.FRANCHISE_MAX_YEAR_INDEX, header.year_field))
            self.year_spin.setEnabled(header.year_field <= fs.FRANCHISE_MAX_YEAR_INDEX)
            guidance = ("The build starting year sets how Studio reads this save. To keep players the same age "
                        "on a modern calendar, use the roster birth-year shift in Build. ")
            # Retail still accepts index 30. Show the build requirement before the next rollover.
            if header.year_field >= 30:
                guidance += ("EXPERIMENTAL / UNWITNESSED. Use the calendar patch with your build's starting year "
                             "for long franchises. A save alone does not identify that patch. ")
            self.season_cap_label.setText(guidance + "Editing this year does not simulate seasons.")
            self.year_spin.setValue(header.display_year)
            self.year_rule_label.setText(
                f"season {header.season_ordinal} = index {header.year_field}; "
                f"{self._base_year} + year field {header.year_field}" +
                (". Outside the editable range 0..127." if header.year_field > fs.FRANCHISE_MAX_YEAR_INDEX else ""))
            if self._document is not None:
                self._document.set_reference_year(header.display_year)
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
                dead = ts.dead_cap(self._save, season.index)
                item = QTableWidgetItem(dead_cap_text(dead[0]) if dead[0] else "-")
                item.setToolTip(self._dead_cap_tip(season.index, dead, season.index in users))
                self.salary_table.setItem(row, 4, item)
            self.salary_table.resizeColumnsToContents()
            self._refresh_dead_cap_button()
        finally:
            self._quiet = False

    def _refresh_schedule(self) -> None:
        self._quiet = True
        try:
            if self._save is None:
                self.schedule_table.setRowCount(0)
                self.week_label.setText("")
                self._refresh_integrity()
                self._fill_game_editor()
                return
            row = self.week_combo.currentIndex()
            rows = range(self._save.regular_season_weeks, fs.GRID_ROWS) if row == fs.GRID_ROWS else [row]
            games = self._save.games(rows=rows) if row >= 0 else []
            selected = self._selected_game()
            selected_cell = (selected.row, selected.slot) if selected else None
            self.schedule_table.setRowCount(len(games))
            for line, game in enumerate(games):
                score = ""
                tip = ""
                if game.scores is not None:
                    # b81 R41: the first five bytes are the home side's (the standings getters read them so);
                    # the score reads away-home like the two columns before it
                    home_q, away_q = game.scores
                    score = f"{sum(away_q)}-{sum(home_q)}"
                    tip = (f"{self._team_short(game.away)} {'-'.join(map(str, away_q))} = {sum(away_q)}, "
                           f"{self._team_short(game.home)} {'-'.join(map(str, home_q))} = {sum(home_q)} "
                           f"(Q1-Q4, OT). Double-click or Box score… to change it.")
                cells = [str(game.slot + 1), self._team_short(game.away) if game.away_known else "To be decided",
                         self._team_short(game.home) if game.home_known else "To be decided",
                         f"{game.month}/{game.day}", game.kickoff(), "yes" if game.played else "", score,
                         game.row_name.title()]
                for column, text in enumerate(cells):
                    item = QTableWidgetItem(text)
                    if tip and column == 6:
                        item.setToolTip(tip)
                    elif game.played:
                        item.setToolTip("This game has been played. Select 'Allow editing played games' to change it.")
                    item.setData(Qt.UserRole, (game.row, game.slot))
                    self.schedule_table.setItem(line, column, item)
            self.schedule_table.resizeColumnsToContents()
            played = sum(1 for g in games if g.played)
            self.week_label.setText(f"{len(games)} games, {played} played")
            self._refresh_integrity()
            if games:
                selected_line = next((i for i, game in enumerate(games)
                                      if (game.row, game.slot) == selected_cell), 0)
                self.schedule_table.selectRow(selected_line)
            self._fill_game_editor()
        finally:
            self._quiet = False

    def _refresh_integrity(self) -> None:
        """The season check under the week table (b81 R8) and which week tools apply to the week shown."""

        regular = (self._save is not None and self._mode == "franchise"
                   and 0 <= self.week_combo.currentIndex() < self._save.regular_season_weeks)
        why = "" if regular else "Playoff rounds come from the bracket; add, remove and clear work on regular-season weeks."
        for button in (self.add_game_button, self.remove_game_button, self.clear_week_button):
            button.setEnabled(regular)
        self.add_game_button.setToolTip(why or "Finn's Add Game: a new game in this week with the teams, date and "
                                               "kick-off above. Refused if either team already plays that week.")
        if self._save is None or self._mode != "franchise":
            self.integrity_label.setText("")
            self.integrity_table.setRowCount(0)
            return
        try:
            report = self._save.schedule_integrity()
        except fs.FranchiseSaveError as exc:
            self.integrity_label.setText(f"Season check unavailable: {exc}")
            self.integrity_table.setRowCount(0)
            return
        self.integrity_label.setText(f"Season check ({report['weeks']} weeks, {report['expected']} games a club): "
                                     + report["summary"])
        self.integrity_table.setRowCount(len(report["rows"]))
        for line, row in enumerate(report["rows"]):
            cells = (row["name"], str(row["home"]), str(row["away"]), str(row["games"]),
                     "; ".join(row["notes"]) or "OK")
            for column, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if column in (1, 2, 3):
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.integrity_table.setItem(line, column, item)
        self.integrity_table.resizeColumnsToContents()

    def schedule_integrity(self) -> dict[str, Any]:
        return self._save.schedule_integrity() if self._save is not None else {}

    def add_game(self, row: int, **fields: int) -> bool:
        """Finn's Add Game through the journal (refusals say why and change nothing)."""

        if self._save is None:
            return False
        names = f"{self._team_short(fields.get('away', 0))} at {self._team_short(fields.get('home', 0))}"
        return self.push(FranchiseEdit("game_add", f"{self._save.schedule_row_name(row).title()}: add {names} "
                                                   f"{fields.get('month')}/{fields.get('day')}",
                                       {"row": row, "fields": dict(fields),
                                        "allow_played": self.allow_played_check.isChecked()}))

    def remove_game(self, row: int, slot: int) -> bool:
        if self._save is None:
            return False
        try:
            game = self._save.game(row, slot)
        except fs.FranchiseSaveError as exc:
            self._set_status(f"Refused: {exc}")
            return False
        names = f"{self._team_short(game.away)} at {self._team_short(game.home)}"
        return self.push(FranchiseEdit("game_remove", f"{game.row_name.title()}: remove {names}",
                                       {"row": row, "slot": slot, "allow_played": self.allow_played_check.isChecked()}))

    def clear_week(self, row: int) -> bool:
        if self._save is None:
            return False
        return self.push(FranchiseEdit("week_clear", f"{self._save.schedule_row_name(row).title()}: clear every game",
                                       {"row": row, "allow_played": self.allow_played_check.isChecked()}))

    def _add_game_clicked(self) -> None:
        row = self.week_combo.currentIndex()
        if self._save is None or not 0 <= row < fs.GRID_ROWS:
            return
        home, away = self.home_combo.currentData(), self.away_combo.currentData()
        if home is None or away is None:
            self._set_status("Choose the away and home teams first.")
            return
        self.add_game(row, home=int(home), away=int(away), month=self.month_spin.value(), day=self.day_spin.value(),
                      hour=self.hour_spin.value(), minute=self.minute_spin.value())

    def _remove_game_clicked(self) -> None:
        game = self._selected_game()
        if game is None:
            self._set_status("Select a game first.")
            return
        self.remove_game(game.row, game.slot)

    def _clear_week_clicked(self) -> None:
        row = self.week_combo.currentIndex()
        if self._save is None or not 0 <= row < fs.GRID_ROWS:
            return
        self.clear_week(row)

    def _selected_game(self) -> fs.Game | None:
        if self._save is None:
            return None
        line = self.schedule_table.currentRow()
        item = self.schedule_table.item(line, 0) if line >= 0 else None
        if item is None:
            return None
        row, slot = item.data(Qt.UserRole)
        return self._save.game(int(row), int(slot))

    def _schedule_row_selected(self) -> None:
        if not self._quiet:
            self._fill_game_editor()

    def _update_game_notice(self) -> None:
        game = self._selected_game()
        if game is None:
            text = "Select a game to edit its date and kickoff time."
        elif game.played:
            text = "This game has been played. " + (
                "Editing is allowed." if self.allow_played_check.isChecked() else
                "Select 'Allow editing played games' before applying changes.") + \
                " Box score… shows and changes its score."
        elif not (game.home_known and game.away_known):
            text = "Teams still to be decided. You can edit the date and kickoff time."
        else:
            text = "You can edit this game's date and kickoff time."
        self.game_notice.setText(text)

    def _fill_game_editor(self) -> None:
        game = self._selected_game()
        was_quiet = self._quiet
        self._quiet = True
        try:
            enabled = game is not None
            for widget in (self.home_combo, self.away_combo, self.month_spin, self.day_spin, self.hour_spin,
                           self.minute_spin, self.apply_game_button, self.swap_button):
                widget.setEnabled(enabled)
            self.box_score_button.setEnabled(game is not None and game.played)
            self._update_game_notice()
            if game is None:
                return
            self.home_combo.setEnabled(game.home_known)
            self.away_combo.setEnabled(game.away_known)
            self.swap_button.setEnabled(game.home_known and game.away_known)
            self.home_combo.setCurrentIndex(self.home_combo.findData(game.home) if game.home_known else -1)
            self.away_combo.setCurrentIndex(self.away_combo.findData(game.away) if game.away_known else -1)
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
                self._refresh_coach_buttons(None)
                self._refresh_formation_totals(None)
                return
            self.coach_name_label.setText(coach.name or f"coach {coach.index}")
            self.coach_info_label.setText(" / ".join(line for line in coach.info if line) or "(no info lines)")
            teams = ", ".join(self._team_label(t) for t in coach.teams) or "not attached to a team"
            self.coach_teams_label.setText(f"Coach record {coach.index} · {teams} · names and info lines are pooled "
                                           f"strings and stay read-only")
            self._refresh_coach_buttons(coach)
            for name, spin in self._coach_spins.items():
                spin.setValue(coach.fields[name])
            for name, card in self._coach_cards.items():
                card.set_value(coach.ratings[name] if name in coach.ratings else coach.tendencies[name])
            self._refresh_formation_totals(coach)
        finally:
            self._quiet = False

    def _refresh_formation_totals(self, coach: fs.Coach | None) -> None:
        """Each set of five formation shares is one distribution; say what this coach's five add up to."""

        for call, label in self._coach_sum_labels.items():
            if coach is None:
                label.setText("")
                continue
            total = sum(coach.tendencies[f"{call}_{formation}"] for formation in fs.COACH_FORMATION_CLASSES)
            label.setText(f"Adds up to {total}." if total == 100 else
                          f"Adds up to {total}. The game's own coaches add up to 100.")

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
            self.ir_table.setRowCount(fs.IR_SLOTS)
            for row in range(fs.IR_SLOTS):
                for column in range(len(IR_COLUMNS)):
                    self.ir_table.setItem(row, column, QTableWidgetItem(""))
            if self._save is None:
                self.place_ir_button.setEnabled(False)
                self.activate_ir_button.setEnabled(False)
                self.ir_returns_label.setText("")
                return
            team = self._ir_team()
            # b780-uxfix: a save with modern injured reserve shows its 20 slots, the games missed, the season-ending
            # flag and whether each player can return (or the game's reason why not); a legacy save its 5 slots
            state = irs.read_state(self._save)
            modern = {e.slot: e for e in state.club(team)} if state.extension else {}
            entries = {e.slot: e for e in self._save.injured_reserve(include_empty=True) if e.team == team}
            slots = irs.CAP if state.extension else fs.IR_SLOTS
            self.ir_table.setRowCount(slots)
            for slot in range(slots):
                detail = modern.get(slot)
                entry = detail or entries.get(slot)
                empty = entry is None or entry.player_index == fs.IR_EMPTY
                cells = [str(slot + 1), "(empty)" if empty else (entry.name or f"#{entry.player_index}"),
                         "" if empty else str(entry.player_index), "", "", ""]
                if detail is not None:
                    cells[3] = str(detail.games_missed) + ("+" if detail.games_missed >= 7 else "")
                    cells[4] = "Yes" if detail.season_ending else "No"
                    cells[5] = "Yes" if detail.can_return else (detail.reason or "No")
                for column, text in enumerate(cells):
                    item = QTableWidgetItem(text)
                    if column == 5 and detail is not None and detail.reason:
                        item.setToolTip(detail.reason)
                    self.ir_table.setItem(slot, column, item)
            self.ir_table.resizeColumnsToContents()
            if state.extension:
                used = state.returns_used[team] if team < len(state.returns_used) else 0
                self.ir_returns_label.setText(
                    f"Returns from injured reserve this season: {used} of {irs.RETURNS} used. A player can come back "
                    f"after missing {irs.MIN_GAMES} games, once he is healthy. Up to {irs.CAP} players a club.")
            else:
                self.ir_returns_label.setText(IR_LEGACY_NOTE)
            for entry in self._save.injured_reserve():
                self.league_ir_list.addItem(f"{self._team_label(entry.team)}: {entry.name or f'#{entry.player_index}'} "
                                            f"(slot {entry.slot + 1}, player #{entry.player_index})")
            self.place_ir_button.setEnabled(True)
            filled = [e for e in (list(entries.values()) + list(modern.values())) if e.player_index != fs.IR_EMPTY]
            self.activate_ir_button.setEnabled(bool(filled))
            self._ir_selection_changed()
        finally:
            self._quiet = False

    def _ir_team(self) -> int:
        data = self.ir_team_combo.currentData()
        return int(data) if data is not None else 0

    def _ir_selection_changed(self) -> None:
        """b780-uxfix: Activate says why the game would refuse the selected player, in the game's own words."""
        tip = "Bring the selected player back to the roster. The game's rules are checked before anything changes."
        heal = (" This is a return from IR (Finn's Activate), not Finn's Heal Player: it does not change an "
                "injury.")
        row = self.ir_table.currentRow()
        item = self.ir_table.item(row, 2) if row >= 0 else None
        if self._save is not None and item is not None and item.text() and irs.read_state(self._save).extension:
            try:
                reason = irs.can_activate(self._save, self._ir_team(), int(item.text()))
            except (ValueError, IndexError):
                reason = None
            if reason:
                tip = f"Can't bring him back yet: {reason}"
        self.activate_ir_button.setToolTip(tip + heal)

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
            lines.append(f"  {status}: {len(regions)} regions, {total:,} bytes, {note}")
            for region in regions:
                extra = f": {region.note}" if region.note else ""
                lines.append(f"    0x{region.offset:06X}..0x{region.end:06X}  {region.label}{extra}")
        lines.append("")
        lines.append("Editable on this page:")
        for what, status, why in EDITABLE_HERE:
            lines.append(f"  {what}: {status}, {why}")
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
        for start, end in ranges[:CHECKS_RANGE_LINES]:
            region = next((r for r in fs.REGIONS if r.offset <= start < r.end), None)
            where = f"{region.label} [{region.status}]" if region else "outside the map"
            lines.append(f"  0x{start:06X}..0x{end:06X} ({end - start} B), {where}")
        if len(ranges) > CHECKS_RANGE_LINES:
            lines.append(f"  ... and {len(ranges) - CHECKS_RANGE_LINES} more ranges (a coach's new name rewrites the coach text)")
        return "\n".join(lines)

    def _refresh_checks(self, *, force: bool = False) -> None:
        if not force and not self._checks_stale:
            return
        self.checks_text.setPlainText(self.checks_text_for())
        self._checks_stale = False

    # ------------------------------------------------------------------ overview edits
    def _base_year_changed(self, year: int) -> None:
        if self._quiet:
            return
        self._base_year = year
        if self._document is not None:
            self._document.base_year = year
        if self._save is not None:
            self._rebuild()
            self._refresh_all()

    def _year_changed(self, year: int) -> None:
        if self._quiet or self._save is None:
            return
        before = self._save.header.display_year
        if before == year:
            return
        index = year - self._base_year
        self.push(FranchiseEdit("year", f"Season year {before} → {year} (season {index + 1} = index {index})",
                                {"year": year, "index": index}))

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
        if (self._save is None or type(year) is not int
                or not 0 <= year - self._base_year <= fs.FRANCHISE_MAX_YEAR_INDEX):
            return False
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
        label = f"{game.row_name.title()} game {slot + 1}: {', '.join(words)}" + (" (played game, allowed)" if game.played else "")
        return self.push(FranchiseEdit("game", label, {"row": row, "slot": slot, "fields": changes, "allow_played": allow}))

    def swap_home_away(self, row: int, slot: int) -> bool:
        if self._save is None:
            return False
        try:
            game = self._save.game(row, slot)
        except fs.FranchiseSaveError as exc:
            self._set_status(f"Refused: {exc}")
            return False
        if game.played:
            # b81 R41: the score halves belong to home and away, so a played game's swap moves them too
            if not self.allow_played_check.isChecked():
                self._last_error = ("this game has been played (its score and flags are in the save); tick "
                                    "'Allow editing played games' to change it anyway")
                self._set_status(f"Refused: {self._last_error}")
                return False
            return self.push(FranchiseEdit(
                "game_swap_played", f"{game.row_name.title()} game {slot + 1}: swap home and away "
                                    f"({self._team_short(game.home)} now away), each club keeps its score",
                {"row": row, "slot": slot}))
        return self.edit_game(row, slot, home=game.away, away=game.home)

    # ------------------------------------------------------------------ b81 R41: box scores
    def edit_box_score(self, row: int, slot: int, home: Sequence[int], away: Sequence[int], *,
                       season_points: bool = True) -> bool:
        """Finn's Boxscore through the journal: the ten quarter bytes, and by default both clubs' season points."""

        if self._save is None:
            return False
        try:
            box = ts.box_score(self._save, row, slot)
        except fs.FranchiseSaveError as exc:
            self._last_error = str(exc)
            self._set_status(f"Refused: {exc}")
            return False
        home, away = [int(v) for v in home], [int(v) for v in away]
        if (tuple(home), tuple(away)) == (box.home_quarters, box.away_quarters):
            self._set_status("Nothing to change on that box score.")
            return False
        label = (f"{self._save.schedule_row_name(row).title()}: box score {self._team_short(box.away)} "
                 f"{box.away_points}-{box.home_points} {self._team_short(box.home)} -> {sum(away)}-{sum(home)}"
                 + ("" if season_points and not box.postseason else " (season points unchanged)"))
        return self.push(FranchiseEdit("box_score", label, {"row": row, "slot": slot, "home": home, "away": away,
                                                            "season_points": bool(season_points)}))

    def box_score_dialog(self, row: int, slot: int) -> BoxScoreDialog | None:
        """The Boxscore dialog for one played game (not shown; ``exec_`` it)."""

        if self._save is None:
            return None
        try:
            box = ts.box_score(self._save, row, slot)
        except fs.FranchiseSaveError as exc:
            self._set_status(f"No box score: {exc}")
            return None
        title = f"{self._save.schedule_row_name(row).title()}, game {slot + 1}"
        return BoxScoreDialog(box, self._team_label(box.away), self._team_label(box.home), title, self)

    def _box_score_clicked(self) -> None:
        game = self._selected_game()
        if game is None or not game.played:
            self._set_status("Select a played game to see its box score.")
            return
        dialog = self.box_score_dialog(game.row, game.slot)
        if dialog is not None and dialog.exec_() == QDialog.Accepted:
            self.edit_box_score(game.row, game.slot, dialog.quarters("home"), dialog.quarters("away"),
                                season_points=dialog.season_points())

    def _apply_game_clicked(self) -> None:
        game = self._selected_game()
        if game is None:
            return
        self.edit_game(game.row, game.slot,
                       home=int(self.home_combo.currentData()) if game.home_known else game.home,
                       away=int(self.away_combo.currentData()) if game.away_known else game.away,
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

    # ------------------------------------------------------------------ head coach moves: swap, fire, hire
    def _fill_coach_list(self, select: int | None = None, *, first_row: bool = False) -> None:
        """The coach list: every league club's head coach in club order, then the coaches no club employs."""

        keep = select
        if keep is None and not first_row:
            row = self.coach_list.currentRow()
            keep = self._coach_rows[row] if 0 <= row < len(self._coach_rows) else None
        self.coach_list.blockSignals(True)
        try:
            self.coach_list.clear()
            self._coach_rows = []
            if self._save is not None:
                coaches = self._save.coaches()
                attached = sorted((c for c in coaches if c.teams), key=lambda c: min(c.teams))
                for coach in attached + [c for c in coaches if not c.teams]:
                    teams = ", ".join(self._team_short(t) for t in coach.teams) or "no team"
                    self.coach_list.addItem(f"{coach.name or f'coach {coach.index}'}: {teams}")
                    self._coach_rows.append(coach.index)
            if self._coach_rows:
                self.coach_list.setCurrentRow(self._coach_rows.index(keep) if keep in self._coach_rows else 0)
        finally:
            self.coach_list.blockSignals(False)

    def _coaches_by_team(self) -> dict[int, fs.Coach]:
        """The head coach of every league club (one decode of the coach table)."""

        if self._save is None:
            return {}
        try:
            by_index = {c.index: c for c in self._save.coaches()}
            heads = self._save.head_coaches()
        except fs.FranchiseSaveError:
            return {}
        return {team: by_index[index] for team, index in heads.items() if index is not None and index in by_index}

    def _refresh_coach_buttons(self, coach: fs.Coach | None) -> None:
        employed = coach is not None and len(coach.teams) == 1
        free = coach is not None and not coach.teams and not coach.placeholder
        self.coach_swap_button.setEnabled(employed)
        self.coach_fire_button.setEnabled(employed)
        self.coach_hire_button.setEnabled(free)
        if coach is None:
            note = ""
        elif len(coach.teams) > 1:
            note = f"{coach.name} leads more than one club in this save, so his record cannot be moved from here."
        elif coach.placeholder:
            note = "This is one of the game's empty coach records. Use Fire and hire on a club to put a new name in a record."
        elif not coach.teams:
            note = f"{coach.name} has no club. Hire him for a club to put him back to work."
        else:
            note = ""
            if coach.other_teams and self._save is not None:
                names = ", ".join(self._team_short(t) for t in coach.other_teams)
                note = f"Exhibition squads ({names}) also use this coach record and keep it when he moves."
        self.coach_move_label.setText(note)

    def _move_labels(self, team: int) -> tuple[str, str]:
        coach = self._coaches_by_team().get(team)
        return self._team_short(team), (coach.name if coach is not None and coach.name else f"the {self._team_short(team)} coach")

    def swap_head_coaches(self, team_a: int, team_b: int, *, restart: bool = True, announcer: bool = True) -> bool:
        """Two clubs exchange head coaches (journaled; a refusal says why and changes nothing)."""

        if self._save is None:
            return False
        if not self.sync_from_roster():
            return False
        try:
            name_a, coach_a = self._move_labels(team_a)
            name_b, coach_b = self._move_labels(team_b)
        except fs.FranchiseSaveError as exc:
            self._set_status(f"Refused: {exc}")
            return False
        label = f"{name_a} and {name_b} swap head coaches: {coach_a} goes to {name_b}, {coach_b} goes to {name_a}"
        return self.push(FranchiseEdit("coach_swap", label, {"a": team_a, "b": team_b, "restart": restart,
                                                             "announcer": announcer}))

    def fire_and_hire(self, team: int, coach_index: int, *, restart: bool = True, announcer: bool = True) -> bool:
        """Fire a club's head coach and hire a coach the save already holds who has no club (he stays on file)."""

        if self._save is None:
            return False
        if not self.sync_from_roster():
            return False
        by_index = {c.index: c for c in self._save.coaches()}
        hired = by_index.get(coach_index)
        if hired is None:
            self._set_status(f"Refused: no coach {coach_index}")
            return False
        name, fired = self._move_labels(team)
        label = f"{name}: {fired} fired, {hired.name or f'coach {coach_index}'} hired"
        return self.push(FranchiseEdit("coach_hire", label, {"team": team, "coach": coach_index, "restart": restart,
                                                              "announcer": announcer}))

    def fire_and_replace(self, team: int, first: str, last: str, bio: Sequence[str] = ()) -> bool:
        """Fire a club's head coach and hire a new person into the same coach record (a named, first-year coach)."""

        if self._save is None:
            return False
        if not self.sync_from_roster():
            return False
        name, fired = self._move_labels(team)
        label = f"{name}: {fired} fired, {' '.join(str(first).split())} {' '.join(str(last).split())} hired (new coach)"
        return self.push(FranchiseEdit("coach_replace", label, {"team": team, "first": str(first), "last": str(last),
                                                                "bio": [str(line) for line in bio]}))

    def _coach_swap_clicked(self) -> None:
        coach = self._current_coach()
        if self._save is None or coach is None or len(coach.teams) != 1:
            return
        team = coach.teams[0]
        mine = self._team_short(team)
        by_team = self._coaches_by_team()
        rows = [(t, f"{self._team_label(t)} · {c.name}") for t, c in by_team.items() if t != team]

        def describe(other: int) -> str:
            theirs = by_team[other].name
            return (f"{coach.name} goes to {self._team_short(other)} and {theirs} goes to {mine}. "
                    "Nobody loses a job.")

        dialog = ClubPickerDialog(f"Swap head coaches: {mine}",
                                  f"Swap {coach.name} ({mine}) with another club's head coach.", rows, describe, self)
        if dialog.exec_() == QDialog.Accepted and dialog.chosen() is not None:
            options = dialog.options()
            self.swap_head_coaches(team, int(dialog.chosen()), restart=options["restart"], announcer=options["announcer"])

    def _coach_fire_clicked(self) -> None:
        coach = self._current_coach()
        if self._save is None or coach is None or len(coach.teams) != 1:
            return
        team = coach.teams[0]
        on_file = [(c.index, f"{c.name} (on file, no club)") for c in self._save.unemployed_coaches()]
        dialog = FireHireDialog(self._team_label(team), coach.name, on_file, self._save.coach_text_problem(), self)
        if dialog.exec_() != QDialog.Accepted:
            return
        choice = dialog.choice()
        if choice is None:
            return
        if choice["kind"] == "file":
            self.fire_and_hire(team, int(choice["coach"]), restart=choice["restart"], announcer=choice["announcer"])
        else:
            self.fire_and_replace(team, choice["first"], choice["last"], choice["bio"])

    def _coach_hire_clicked(self) -> None:
        coach = self._current_coach()
        if self._save is None or coach is None or coach.teams or coach.placeholder:
            return
        by_team = self._coaches_by_team()
        rows = [(t, f"{self._team_label(t)} · {c.name}") for t, c in by_team.items()]

        def describe(team: int) -> str:
            return (f"{by_team[team].name} is fired and stays on file. {coach.name} becomes head coach of "
                    f"{self._team_short(team)}.")

        dialog = ClubPickerDialog(f"Hire {coach.name}", f"Which club hires {coach.name}? Its head coach is fired.",
                                  rows, describe, self)
        if dialog.exec_() == QDialog.Accepted and dialog.chosen() is not None:
            options = dialog.options()
            self.fire_and_hire(int(dialog.chosen()), coach.index, restart=options["restart"], announcer=options["announcer"])

    # ------------------------------------------------------------------ Finn's coach file: export and import (b81 R2, G5)
    def export_coaches_text(self) -> str:
        """Every league club's head coach in Finn's .Coaches format (current state, roster edits included)."""

        if self._save is None or not self.sync_from_roster():
            return ""
        return cf.export_coaches(self._save)

    def export_coaches_to(self, path: Path | str) -> Path:
        """Write Finn's coach file; the extension is ``.Coaches`` unless the name already has one of Finn's two."""

        target = Path(path)
        if target.suffix.lower() not in (e.lower() for e in cf.OPEN_EXTENSIONS):
            target = target.with_name(target.name + cf.EXTENSION)
        text = self.export_coaches_text()
        if not text:
            raise fs.FranchiseSaveError("no coaches to export")
        target.write_bytes(cf.encode_file(text))
        self._set_status(f"Exported {text.count('[')} head coaches to {target.name}.")
        return target

    def plan_coach_import(self, text: str) -> cf.ImportPlan | None:
        if self._save is None or not self.sync_from_roster():
            return None
        return cf.plan_import(self._save, text)

    def coach_import_dialog(self, text: str, file_name: str = "coach file") -> CoachImportDialog | None:
        plan = self.plan_coach_import(text)
        return None if plan is None else CoachImportDialog(plan, file_name, self)

    def import_coaches(self, text: str) -> bool:
        """Apply a Finn coach file as ONE journaled edit; a refusal says why and changes nothing."""

        plan = self.plan_coach_import(text)
        if plan is None:
            return False
        if plan.refusals:
            self._last_error = plan.refusals[0]
            self._set_status(f"Refused: {plan.refusals[0]}")
            return False
        if not plan.changes:
            self._set_status("Nothing in the coach file differs from this save.")
            return False
        try:                                    # a dry run on a private copy: what the writer will really do with the names
            trial = self._new_save(self._save.to_bytes())
            receipt = cf.apply_import(trial, cf.plan_import(trial, text))
        except ValueError as exc:
            self._last_error = str(exc)
            self._set_status(f"Refused: {exc}")
            return False
        clubs = len({c.team for c in plan.changes})
        label = (f"Import coaches: {receipt['changes_written']} change{'s' if receipt['changes_written'] != 1 else ''} "
                 f"to {clubs} club{'s' if clubs != 1 else ''}' head coach{'es' if clubs != 1 else ''}")
        if receipt["names_skipped"]:
            label += f" ({len(receipt['names_skipped'])} name change{'s' if len(receipt['names_skipped']) != 1 else ''} skipped)"
        self.last_import_receipt = receipt
        return self.push(FranchiseEdit("coaches_import", label, {"text": text}))

    def _export_coaches_clicked(self) -> None:
        if self._save is None:
            return
        path, _filter = QFileDialog.getSaveFileName(self, "Export coaches", "coaches" + cf.EXTENSION, cf.FILE_FILTER)
        if not path:
            return
        try:
            self.export_coaches_to(path)
        except (OSError, ValueError) as exc:
            self._set_status(f"Could not export: {plain_error(exc)}")

    def _import_coaches_clicked(self) -> None:
        if self._save is None:
            return
        path, _filter = QFileDialog.getOpenFileName(self, "Import coaches", "", cf.FILE_FILTER)
        if not path:
            return
        try:
            text = cf.decode_file(Path(path).read_bytes())
        except OSError as exc:
            self._set_status(f"Could not read the file: {plain_error(exc)}")
            return
        dialog = self.coach_import_dialog(text, Path(path).name)
        if dialog is not None and dialog.exec_() == QDialog.Accepted:
            self.import_coaches(text)
        elif dialog is not None and dialog.plan.refusals:
            self._set_status(f"Refused: {dialog.plan.refusals[0]}")

    # ------------------------------------------------------------------ dead cap (b81 R2, F9)
    def _season_label(self, offset: int) -> str:
        assert self._save is not None
        year = self._save.header.display_year + offset
        return f"{year} (this season)" if offset == 0 else str(year)

    def _dead_cap_tip(self, team: int, dead: Sequence[int], controlled: bool) -> str:
        assert self._save is not None
        lines = [f"{self._season_label(k)}: {dead_cap_text(v) if v else 'none'}" for k, v in enumerate(dead)]
        lines.append("Only clubs a person controls ever pile up dead cap in the game (released players' unpaid bonus). "
                     + ("This club is user-controlled." if controlled else "This club is run by the CPU."))
        return "\n".join(lines)

    def _selected_team_row(self) -> int | None:
        row = self.salary_table.currentRow()
        if self._save is None or self._mode != "franchise" or not 0 <= row < self.salary_table.rowCount():
            return None
        return row

    def _refresh_dead_cap_button(self) -> None:
        team = self._selected_team_row()
        dead = ts.dead_cap(self._save, team) if team is not None and self._save is not None else ()
        self.clear_cap_button.setEnabled(any(dead))
        if self._save is None or self._mode != "franchise":
            self.dead_cap_label.setText("")
        elif team is None:
            self.dead_cap_label.setText("Pick a club in the table to see its dead cap.")
        elif not any(dead):
            self.dead_cap_label.setText(f"{self._team_short(team)} has no dead cap.")
        else:
            self.dead_cap_label.setText(f"{self._team_short(team)} dead cap: " + ", ".join(
                f"{self._season_label(k)} {dead_cap_text(v)}" for k, v in enumerate(dead) if v))

    def cap_penalty_text(self, team: int) -> str:
        """The confirmation: each season's amount that Clear cap penalty would zero."""

        assert self._save is not None
        dead = ts.dead_cap(self._save, team)
        rows = "\n".join(f"  {self._season_label(k)}: {dead_cap_text(v)}" for k, v in enumerate(dead) if v)
        return (f"Clear the cap penalty of the {self._team_short(team)}?\n\n{rows}\n\nEvery season's dead cap goes to "
                "zero, so the club has that cap space back. Undo takes it back.")

    def clear_cap_penalty(self, team: int) -> bool:
        """Finn's Clear Cap Penalty for a club, all seven seasons, as one journaled edit."""

        if self._save is None or self._mode != "franchise" or not self.sync_from_roster():
            return False
        if not 0 <= team < self._save.league_team_count:
            self._set_status(f"Refused: team {team} is not a league club")
            return False
        dead = ts.dead_cap(self._save, team)
        if not any(dead):
            self._set_status(f"{self._team_short(team)} has no dead cap to clear.")
            return False
        seasons = ", ".join(f"{self._season_label(k)} {dead_cap_text(v)}" for k, v in enumerate(dead) if v)
        return self.push(FranchiseEdit("dead_cap_clear", f"{self._team_short(team)}: cap penalty cleared ({seasons})",
                                       {"team": team}))

    def _clear_cap_clicked(self) -> None:
        team = self._selected_team_row()
        if team is None or self._save is None or not any(ts.dead_cap(self._save, team)):
            return
        if QMessageBox.question(self, "Clear cap penalty", self.cap_penalty_text(team)) == QMessageBox.Yes:
            self.clear_cap_penalty(team)

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

    def _place_ir_clicked(self, _checked: bool = False, *, selected: int | None = None) -> bool:
        if self._save is None:
            return False
        team = self._ir_team()
        dialog = IrPickerDialog(self._team_label(team), self.ir_candidates(team), self, selected=selected)
        if dialog.exec_() == QDialog.Accepted:
            chosen = dialog.chosen()
            if chosen is not None:
                return self.place_on_ir(team, chosen)
        return False

    def show_injured_reserve(self, team: int) -> bool:
        """b81 (Finn parity): bring up Franchise > Injured Reserve on ``team``, the way the Rosters grid's
        right-click Place on IR… arrives here. Returns False when no franchise save is loaded."""

        if self._save is None:
            return False
        if self._host is not None:
            self._host.setCurrentIndex(self._host_index)
        self.tabs.setCurrentIndex(self._ir_tab_index)
        index = self.ir_team_combo.findData(int(team))
        if index >= 0:
            self.ir_team_combo.setCurrentIndex(index)
        return index >= 0

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
        warning = self._document.college_warning if self._document is not None else ""
        self.status_label.setText(text + ("\n" + warning if warning else ""))

    @property
    def last_error(self) -> str:
        return self._last_error


__all__ = ["COACH_STATS", "ClubPickerDialog", "EDITABLE_HERE", "FireHireDialog", "FranchiseEdit", "FranchisePanel",
           "IrPickerDialog", "CoachImportDialog", "dead_cap_text", "money"]
