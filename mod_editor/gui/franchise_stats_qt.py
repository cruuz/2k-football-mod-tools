"""Finn's Team Statistics tab and Boxscore editor on the Franchise page (b81 R41, parity rows I2 and H7).

Everything read or written here goes through ``mod_editor.core.nfl2k5_team_stats``; no offset lives in this file.
``TeamStatsPage`` is read-only, as Finn's is.  ``BoxScoreDialog`` only collects numbers; the Franchise page journals
the change (one undo step) and the core writer checks it again before any byte changes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Sequence

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mod_editor.core import nfl2k5_franchise_save as fs
from mod_editor.core import nfl2k5_team_stats as ts

STATS_INTRO = ("The season numbers the game keeps for each club, the way Finn's Stats tab shows them. They are read "
               "from the save and cannot be typed over here: the game adds each game's numbers when it is played. "
               "W-L-T is counted from the box scores, as the game's standings are. Click a heading to sort.")
STATS_NOTE = ("AVG PASS and AVG RUSH divide by pass plays and rushing plays (the season numbers the save keeps), so "
              "they can differ a little from the game's own box score, which divides by attempts and carries. "
              "A dash means there is nothing to divide by yet.")
BOX_NOTE = ("The game counts each club's wins, losses and ties from these numbers, so the standings follow this "
            "change. Yards and the other season numbers stay as the game added them.")
BOX_PLAYOFF_NOTE = ("A playoff game keeps its winner: the bracket has already moved the winner on. Its season "
                    "points are not changed.")


class _SortItem(QTableWidgetItem):
    """A cell that sorts by its number (a dash, no value, sorts lowest) and shows the formatted text."""

    def __init__(self, text: str, key: object) -> None:
        super().__init__(text)
        self.setData(Qt.UserRole, key)
        self.setFlags(self.flags() & ~Qt.ItemIsEditable)

    def __lt__(self, other: QTableWidgetItem) -> bool:  # noqa: D105 - Qt sort hook
        mine, theirs = self.data(Qt.UserRole), other.data(Qt.UserRole)
        if isinstance(mine, (int, float)) and isinstance(theirs, (int, float)):
            return mine < theirs
        if mine is None or theirs is None:
            return mine is None and theirs is not None
        return str(mine) < str(theirs)


def _record_key(record: tuple[int, int, int]) -> float:
    """Sort a W-L-T by winning share (a tie is half a win), then by wins."""

    games = sum(record)
    return ((record[0] + record[2] / 2) / games if games else 0.0) + record[0] / 1000.0


class TeamStatsPage(QWidget):
    """Finn's Team Statistics grid: 32 clubs, W-L-T and games played, his 31 columns, then the two-point counters."""

    COLUMNS: tuple[ts.StatColumn, ...] = ts.FINN_COLUMNS + ts.EXTRA_COLUMNS
    LEAD = ("Team", "W-L-T", "GP")

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._save: fs.FranchiseSave | None = None
        self._label: Callable[[int], str] = lambda team: str(team)
        layout = QVBoxLayout(self)
        intro = QLabel(STATS_INTRO)
        intro.setWordWrap(True)
        layout.addWidget(intro)
        self.table = QTableWidget(0, len(self.LEAD) + len(self.COLUMNS))
        self.table.setAccessibleName("Team season statistics")
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        headers = list(self.LEAD) + [column.caption for column in self.COLUMNS]
        self.table.setHorizontalHeaderLabels(headers)
        self.table.horizontalHeader().setSortIndicator(0, Qt.AscendingOrder)
        self.table.horizontalHeader().setSortIndicatorShown(True)
        tips = ["Club", "Wins, losses and ties, counted from the box scores the way the game's standings count them",
                "Games played (the game's own counter)"]
        tips += [column.title + (f". {column.note}" if column.note else "") for column in self.COLUMNS]
        for index, tip in enumerate(tips):
            self.table.horizontalHeaderItem(index).setToolTip(tip)
        layout.addWidget(self.table, 1)
        row = QHBoxLayout()
        self.note_label = QLabel(STATS_NOTE)
        self.note_label.setWordWrap(True)
        row.addWidget(self.note_label, 1)
        self.export_button = QPushButton("Export as CSV…")
        self.export_button.setToolTip("Save this table as a CSV file (opens in Excel).")
        self.export_button.clicked.connect(lambda: self.export_csv())
        row.addWidget(self.export_button)
        layout.addLayout(row)
        self.refresh(None)

    def refresh(self, save: fs.FranchiseSave | None, label: Callable[[int], str] | None = None) -> None:
        self._save = save
        if label is not None:
            self._label = label
        header = self.table.horizontalHeader()
        sort_column, sort_order = header.sortIndicatorSection(), header.sortIndicatorOrder()
        self.table.setSortingEnabled(False)
        rows = ts.league_table(save, self.COLUMNS) if save is not None else []
        self.table.setRowCount(len(rows))
        for line, entry in enumerate(rows):
            cells: list[tuple[str, object]] = [(self._label(entry.team), entry.team),
                                               (entry.record_text, _record_key(entry.record)),
                                               (str(entry.games_played), entry.games_played)]
            for column in self.COLUMNS:
                value = entry.values[column.key]
                cells.append((ts.format_value(value, column), value))
            for index, (text, key) in enumerate(cells):
                item = _SortItem(text, key)
                if index:
                    item.setTextAlignment(int(Qt.AlignRight | Qt.AlignVCenter))
                self.table.setItem(line, index, item)
        self.table.setSortingEnabled(True)
        # the club column sorts by team index, so its ascending order is the game's own club order (the default)
        if not 0 <= sort_column < self.table.columnCount():
            sort_column, sort_order = 0, Qt.AscendingOrder
        self.table.sortItems(sort_column, sort_order)
        self.table.resizeColumnsToContents()
        self.export_button.setEnabled(save is not None)

    def team_order(self) -> None:
        """Back to the game's club order."""

        self.table.sortItems(0, Qt.AscendingOrder)

    def row_texts(self) -> list[list[str]]:
        """The table as shown (for tests and printing)."""

        return [[self.table.item(r, c).text() for c in range(self.table.columnCount())]
                for r in range(self.table.rowCount())]

    def export_csv(self, path: Path | str | None = None) -> Path | None:
        if self._save is None:
            return None
        if path is None:
            chosen, _ = QFileDialog.getSaveFileName(self, "Export team statistics", "team-stats.csv", "CSV (*.csv)")
            if not chosen:
                return None
            path = chosen
        target = Path(path)
        target.write_text(ts.csv_text(self._save, self.COLUMNS), encoding="utf-8", newline="")
        return target


class BoxScoreDialog(QDialog):
    """Finn's Boxscore: both clubs' five quarter scores and finals, editable for a played game."""

    def __init__(self, box: ts.BoxScore, away_name: str, home_name: str, title: str,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.box = box
        self.setWindowTitle(f"Box score: {title}")
        layout = QVBoxLayout(self)
        layout.setSizeConstraint(QLayout.SetFixedSize)         # its own size hint: large text never squeezes a row
        heading = QLabel(f"{title}: {away_name} at {home_name}")
        font = heading.font()
        font.setBold(True)
        heading.setFont(font)
        layout.addWidget(heading)
        grid = QGridLayout()
        for column, caption in enumerate(ts.QUARTERS + ("Final",), start=1):
            label = QLabel(caption)
            label.setAlignment(Qt.AlignCenter)
            grid.addWidget(label, 0, column)
        self.spins: dict[str, list[QSpinBox]] = {}
        self.finals: dict[str, QLabel] = {}
        for line, (side, name, values) in enumerate((("away", away_name, box.away_quarters),
                                                    ("home", home_name, box.home_quarters)), start=1):
            grid.addWidget(QLabel(name), line, 0)
            spins = []
            for column, (quarter, value) in enumerate(zip(ts.QUARTERS, values), start=1):
                spin = QSpinBox()
                spin.setRange(0, ts.SCORE_MAX)
                spin.setValue(int(value))
                spin.setAccessibleName(f"{name} {quarter}")
                spin.valueChanged.connect(lambda _v: self._update())
                grid.addWidget(spin, line, column)
                spins.append(spin)
            self.spins[side] = spins
            final = QLabel("")
            final.setAlignment(Qt.AlignCenter)
            final.setAccessibleName(f"{name} final")
            grid.addWidget(final, line, len(ts.QUARTERS) + 1)
            self.finals[side] = final
        layout.addLayout(grid)
        self.season_points_check = QCheckBox("Also change both clubs' season points (Team Stats TPS and TPSA)")
        self.season_points_check.setChecked(not box.postseason)
        self.season_points_check.setEnabled(not box.postseason)
        self.season_points_check.setToolTip(
            "Moves each club's points scored and points allowed by the change, so the season totals stay equal to "
            "the sum of the club's box scores, as the game keeps them." if not box.postseason else BOX_PLAYOFF_NOTE)
        layout.addWidget(self.season_points_check)
        note = QLabel(BOX_NOTE + (" " + BOX_PLAYOFF_NOTE if box.postseason else ""))
        note.setWordWrap(True)
        layout.addWidget(note)
        self.result_label = QLabel("")
        self.result_label.setWordWrap(True)
        self.result_label.setAccessibleName("Box score result")
        layout.addWidget(self.result_label)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Ok).setText("Apply")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self._names = {"away": away_name, "home": home_name}
        self._update()

    def quarters(self, side: str) -> tuple[int, ...]:
        return tuple(spin.value() for spin in self.spins[side])

    def set_quarters(self, side: str, values: Sequence[int]) -> None:
        for spin, value in zip(self.spins[side], values):
            spin.setValue(int(value))

    def season_points(self) -> bool:
        return self.season_points_check.isChecked()

    def changed(self) -> bool:
        return (self.quarters("home"), self.quarters("away")) != (self.box.home_quarters, self.box.away_quarters)

    def problem(self) -> str:
        """Why Apply is off, in words; empty when the numbers can be written."""

        if not self.changed():
            return "No change yet."
        if self.box.postseason:
            home, away = sum(self.quarters("home")), sum(self.quarters("away"))
            if home == away:
                return "A playoff game cannot end in a tie."
            if (home > away) != (self.box.winner == "home"):
                return "A playoff game keeps its winner: the bracket has already moved the winner on."
        return ""

    def _update(self) -> None:
        totals = {side: sum(self.quarters(side)) for side in ("away", "home")}
        for side, label in self.finals.items():
            label.setText(str(totals[side]))
        away, home = totals["away"], totals["home"]
        if away == home:
            result = f"Tie, {away}-{home}."
        else:
            winner = "away" if away > home else "home"
            result = f"{self._names[winner]} win {max(away, home)}-{min(away, home)}."
        problem = self.problem()
        self.result_label.setText(result + ("" if not problem or problem == "No change yet." else f" {problem}"))
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(not problem)
        self.buttons.button(QDialogButtonBox.Ok).setToolTip(problem)
