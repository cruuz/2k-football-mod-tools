"""Install / Export dialogs for community playbook packs (``.2k5book``).

The install flow is: pick a file, read the plan (what each entry replaces and
whether it is OK, in conflict with an edit you already staged, or over budget),
watch the live budget bar (plays n/270, formations n/50, nodes n/3,500), choose
the team assignment (the pack's own team, a retarget, or all 32 team books), and
stage.  Staged pack rows are ordinary project edits: they show in the edit list,
revert one by one, and save into ``.2k5mod`` with no schema change.

The table, the budget bar and the team list are built by the pure functions at
the top of this module so they can be exercised without a screen.
"""

from __future__ import annotations

from mod_editor.gui.ux_text import failure_body

from pathlib import Path
from typing import Any, Callable, Sequence

from mod_editor.core import nfl2k5_playbook_pack as pack_mod

ProgressSink = Callable[[str, int, int], None]


def _quiet(_message: str, _done: int = 0, _total: int = 0) -> None:
    return None


PLAN_COLUMNS = ("What", "Name", "Replaces", "Status", "Why")

#: What the format honestly cannot do, shown on every install so nobody ships a
#: pack promising it (the engine limits, not the studio's).
ENGINE_LIMITS_TEXT = (
    "What the engine cannot do, whatever a pack says: no pre-snap motion, no "
    "give-or-throw RPO (the ball sim walks each chain once, so a quarterback who "
    "hands off cannot throw later), and no tempo / no-huddle. Option routes and "
    "keep-or-throw RPOs are accepted by the ported retail validator but have "
    "never been witnessed in game."
)


def pack_summary_lines(pack: pack_mod.PlaybookPack) -> tuple[str, ...]:
    """Header lines for one pack: who made it, what it is, what it starts from."""

    lines = [
        f"{pack.book.name}  —  v{pack.book.version} by {pack.book.author}  ({pack.book.license})",
        f"Authored on {pack.book.team}: {len(pack.formations)} formation(s), {len(pack.plays)} play(s); "
        f"started from a book with {pack.base.donor_formation_count} formations, "
        f"{pack.base.donor_play_count} plays, {pack.base.donor_node_count} nodes "
        f"(fingerprint {pack.base.book_fingerprint[:12]}…)",
    ]
    if any(p.play_type == "defense" for p in pack.plays):
        from mod_editor.core import nfl2k5_play_library as lib
        totals = pack_mod.budget_totals(pack)
        lines.append(f"{lib.DEFENSE_EVIDENCE}. Cloned nodes {totals['cloned_nodes']}; "
                     f"node pool {totals['node_pool_bytes']} bytes, names {totals['name_pool_bytes']} bytes.")
        lines.append(lib.SPY_NOTICE)
    if pack.book.notes:
        lines.append(pack.book.notes)
    return tuple(lines)


def team_choices(pack: pack_mod.PlaybookPack, available: Sequence[str]) -> tuple[tuple[str, object], ...]:
    """(label, value) pairs for the team-assignment combo.

    ``value`` is a team name, or the :data:`nfl2k5_playbook_pack.ALL_TEAMS`
    marker for "every team book"."""

    choices: list[tuple[str, object]] = []
    if pack.book.team in available:
        choices.append((f"As authored — {pack.book.team}", pack.book.team))
    if any(p.option_intent for p in pack.plays):
        return tuple(choices)
    for team in available:
        if team == pack.book.team:
            continue
        choices.append((f"Retarget to {team}", team))
    if pack.schema == pack_mod.DEFENSE_SCHEMA and pack.book.targets:
        targets = tuple(t for t in pack.book.resolved_targets() if t in available)
        if targets:
            choices.append((f"Pack targets ({len(targets)} books)", targets))
    if available:
        choices.append((f"All {len(available)} team books", tuple(available) if pack.schema == pack_mod.DEFENSE_SCHEMA else pack_mod.ALL_TEAMS))
    return tuple(choices)


def plan_table_rows(preview: pack_mod.PackPreview) -> tuple[tuple[str, ...], ...]:
    """One display row per pack entry, in :data:`PLAN_COLUMNS` order."""

    return tuple(
        (row.kind, row.name, row.replaces, row.status, row.detail)
        for row in preview.plan.rows
    )


def budget_bars(totals: dict[str, Any] | Any) -> tuple[tuple[str, int, int], ...]:
    """(label, value, maximum) for the three budget bars."""

    return (
        ("plays", int(totals["plays"]), int(totals["play_capacity"])),
        ("formations", int(totals["formations"]), int(totals["formation_capacity"])),
        ("nodes", int(totals["nodes"]), int(totals["node_capacity"])),
    )


def install_blockers(preview: pack_mod.PackPreview) -> tuple[str, ...]:
    """Every reason this preview cannot be staged, in the order to show them."""

    reasons: list[str] = []
    for row in preview.plan.rows:
        if row.status not in ("ok", "retargeted"):
            reasons.append(f"{row.kind} “{row.name}”: {row.status} — {row.detail}")
    reasons.extend(preview.plan.blocked)
    reasons.extend(preview.check.errors)
    return tuple(reasons)


#: The 2004 team names behind the 32 retail book keys (the keys Build and the pack format use).
BOOK_SET_TEAM_NAMES: dict[str, str] = {
    "ARZ": "Arizona Cardinals", "ATL": "Atlanta Falcons", "BAL": "Baltimore Ravens",
    "BUF": "Buffalo Bills", "CAR": "Carolina Panthers", "CHI": "Chicago Bears",
    "CIN": "Cincinnati Bengals", "CLE": "Cleveland Browns", "DAL": "Dallas Cowboys",
    "DEN": "Denver Broncos", "DET": "Detroit Lions", "GB": "Green Bay Packers",
    "HOU": "Houston Texans", "IND": "Indianapolis Colts", "JAX": "Jacksonville Jaguars",
    "KC": "Kansas City Chiefs", "MIA": "Miami Dolphins", "MIN": "Minnesota Vikings",
    "NE": "New England Patriots", "NO": "New Orleans Saints", "NYG": "New York Giants",
    "NYJ": "New York Jets", "OAK": "Oakland Raiders", "PHI": "Philadelphia Eagles",
    "PIT": "Pittsburgh Steelers", "SD": "San Diego Chargers", "SEA": "Seattle Seahawks",
    "SF": "San Francisco 49ers", "STL": "St. Louis Rams", "TB": "Tampa Bay Buccaneers",
    "TEN": "Tennessee Titans", "WAS": "Washington",
}

#: One sentence that says what Modern and Classic mean, shown beside both book-set controls.
BOOK_SET_EXPLAINER = (
    "Modern is the SOFTDRINK 2026 playbook (offense and defense together). Classic is the original "
    "2004 book. The choice is used when you press Make my disc; for the 2004 books, build from your "
    "original retail disc."
)


def book_set_status_text(info: dict[str, object] | None) -> str:
    """The line "Modern 32, Classic 0" for a book-set reader's status (None: no disc yet)."""

    if not info:
        return "Open your game disc (top right) to choose modern or classic books."
    text = f"Modern {info['modern_count']}, Classic {info['classic_count']}"
    incomplete = tuple(info.get("incomplete_teams") or ())
    if incomplete:
        text += f", half-set {len(incomplete)} ({', '.join(incomplete)})"
    return text


from PyQt5.QtCore import Qt  # noqa: E402
from PyQt5.QtWidgets import (  # noqa: E402
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QGridLayout, QPushButton, QDialogButtonBox, QFileDialog, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QProgressBar, QTableWidget,
    QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget,
)

_STATUS_COLOURS = {"ok": "#1a7f37", "retargeted": "#8a6d00", "conflict": "#b42318",
                   "over budget": "#b42318"}


class PlaybookPackInstallDialog(QDialog):
    """Pick a ``.2k5book``, read its plan, choose the team, stage it."""

    def __init__(self, host: Any, path: Path | str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.host = host
        self.path = Path(path)
        self.pack = host.load_playbook_pack(self.path)
        self.preview: pack_mod.PackPreview | None = None
        self.installed_teams: tuple[str, ...] = ()
        self.setWindowTitle(f"Install Playbook Pack — {self.pack.book.name}")
        self.setMinimumSize(940, 640)

        layout = QVBoxLayout(self)
        self.summary = QLabel("\n".join(pack_summary_lines(self.pack)))
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)

        team_row = QHBoxLayout()
        team_row.addWidget(QLabel("Put it in:"))
        self.team_combo = QComboBox()
        try:
            available = list(host.playbook_teams())
            if self.pack.schema == pack_mod.DEFENSE_SCHEMA and hasattr(host, "browse_playbooks"):
                available = [b.book_name for b in host.browse_playbooks("", _quiet)
                             if b.book_name in pack_mod.DEFENSE_BOOKS]
        except Exception:  # noqa: BLE001 - a host without a source still opens the dialog
            available = []
        for label, value in team_choices(self.pack, available):
            self.team_combo.addItem(label, value)
        team_row.addWidget(self.team_combo, 1)
        layout.addLayout(team_row)

        self.table = QTableWidget(0, len(PLAN_COLUMNS))
        self.table.setHorizontalHeaderLabels(PLAN_COLUMNS)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table, 1)

        bars = QFormLayout()
        self.bars: dict[str, QProgressBar] = {}
        for key in ("plays", "formations", "nodes"):
            bar = QProgressBar()
            bar.setTextVisible(True)
            self.bars[key] = bar
            bars.addRow(key.capitalize(), bar)
        layout.addLayout(bars)

        self.status = QLabel("")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        limits = QLabel(("Defense uses retail front and coverage pairs. New calls are EXPERIMENTAL / UNWITNESSED. "
                         + pack_mod.lib.SPY_NOTICE) if any(p.play_type == 'defense' for p in self.pack.plays) else ENGINE_LIMITS_TEXT)
        limits.setWordWrap(True)
        limits.setObjectName("playBoundary")
        layout.addWidget(limits)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Ok).setText("Install into the project")
        self.buttons.accepted.connect(self._install)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

        self.team_combo.currentIndexChanged.connect(lambda _i: self.refresh())
        self.refresh()

    # -- model ------------------------------------------------------------------
    def selected_teams(self) -> tuple[str, ...]:
        value = self.team_combo.currentData()
        if isinstance(value, (tuple, list)):
            return tuple(value)
        if value == pack_mod.ALL_TEAMS:
            try:
                return tuple(self.host.playbook_teams())
            except Exception:  # noqa: BLE001
                return ()
        return (str(value),) if value else ()

    def preview_team(self) -> str:
        teams = self.selected_teams()
        return teams[0] if teams else self.pack.book.team

    def refresh(self) -> None:
        team = self.preview_team()
        try:
            self.preview = self.host.preview_playbook_pack(self.pack, team, _quiet)
        except Exception as exc:  # noqa: BLE001 - shown, never raised out of a dialog
            self.preview = None
            self.table.setRowCount(0)
            self.status.setText(str(exc))
            self.buttons.button(QDialogButtonBox.Ok).setEnabled(False)
            return
        rows = plan_table_rows(self.preview)
        self.table.setRowCount(len(rows))
        for r, values in enumerate(rows):
            for c, text in enumerate(values):
                item = QTableWidgetItem(text)
                if c == 3:
                    colour = _STATUS_COLOURS.get(text)
                    if colour:
                        item.setForeground(Qt.red if colour == "#b42318" else Qt.darkGreen)
                self.table.setItem(r, c, item)
        self.table.resizeColumnsToContents()
        for key, value, maximum in budget_bars(self.preview.plan.totals):
            bar = self.bars[key]
            bar.setMaximum(maximum)
            bar.setValue(min(value, maximum))
            bar.setFormat(f"{value}/{maximum}")
        blockers = install_blockers(self.preview)
        multi = len(self.selected_teams()) > 1
        if blockers:
            self.status.setText("Cannot install yet:\n• " + "\n• ".join(blockers[:6]))
        else:
            note = self.preview.plan.budget_line()
            if self.preview.retargeted:
                changed = sum(1 for r in self.preview.resolutions if r.how == "ranked")
                note += (f"  —  retargeted to {team}"
                         + (f", {changed} entry target(s) re-resolved by rank" if changed else ""))
            if multi:
                note += f"  —  will be staged into all {len(self.selected_teams())} team books"
            self.status.setText(note)
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(not blockers)

    # -- action -----------------------------------------------------------------
    def _install(self) -> None:
        teams = self.selected_teams()
        if not teams:
            QMessageBox.information(self, "Install Playbook Pack", "Choose a team first.")
            return
        try:
            # Refuse the smallest target before staging any of the selected books.
            if self.pack.schema == pack_mod.DEFENSE_SCHEMA:
                for team in teams:
                    preview = self.host.preview_playbook_pack(self.pack, team, _quiet)
                    blocked = install_blockers(preview)
                    if blocked:
                        raise pack_mod.PlaybookPackError(f"{team}: {blocked[0]}")
            result = self.host.install_playbook_pack(self.pack, teams, _quiet)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Couldn't finish that", failure_body(exc))
            return
        self.installed_teams = teams
        self.result_message = str(getattr(result, "message", result))
        self.accept()


class PlaybookPackExportDialog(QDialog):
    """Name / author / version / licence for a pack exported from staged rows."""

    def __init__(self, book_name: str, staged: int | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Export Playbook Pack")
        self.result_payload: dict[str, str] | None = None
        layout = QVBoxLayout(self)
        counted = f"{staged} staged edit(s)" if staged else "The formations and plays you designed"
        layout.addWidget(QLabel(
            f"{counted} in {book_name} become a shareable .2k5book recipe. "
            "It carries no game data: only your formations, plays, names and the donor "
            "indices they came from."
        ))
        form = QFormLayout()
        self.name = QLineEdit(f"{book_name} playbook pack")
        self.author = QLineEdit()
        self.author.setPlaceholderText("your name or Discord handle")
        self.version = QLineEdit("1.0.0")
        self.license = QLineEdit("CC0-1.0")
        self.license.setToolTip("How others may use your pack.")
        self.notes = QTextEdit()
        self.notes.setPlaceholderText("What is in it, what it replaces, what you tested.")
        self.notes.setMaximumHeight(90)
        form.addRow("Name", self.name)
        form.addRow("Author", self.author)
        form.addRow("Version", self.version)
        form.addRow("Licence", self.license)
        form.addRow("Notes", self.notes)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Save pack as…")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _accept(self) -> None:
        if not self.name.text().strip():
            QMessageBox.information(self, "Export Playbook Pack", "Give the pack a name.")
            return
        self.result_payload = {
            "name": self.name.text().strip(),
            "author": self.author.text().strip() or "unknown",
            "version": self.version.text().strip() or "1.0.0",
            "license": self.license.text().strip() or "CC0-1.0",
            "notes": self.notes.toPlainText().strip(),
        }
        self.accept()


class BookSetTeamsDialog(QDialog):
    """Tick the teams that get the modern SOFTDRINK book; the rest keep the classic 2004 book."""

    def __init__(self, info: dict[str, object], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Choose teams for the modern books")
        modern = set(info.get("modern_teams") or ())
        half = set(info.get("incomplete_teams") or ())
        layout = QVBoxLayout(self)
        intro = QLabel("Tick every team that should get the modern SOFTDRINK book. " + BOOK_SET_EXPLAINER)
        intro.setWordWrap(True)
        layout.addWidget(intro)
        grid = QGridLayout()
        self.checks: dict[str, QCheckBox] = {}
        for index, team in enumerate(pack_mod.TEAM_BOOKS):
            label = f"{team}  {BOOK_SET_TEAM_NAMES.get(team, '')}".rstrip()
            if team in half:
                label += " (half set)"
            box = QCheckBox(label)
            box.setChecked(team in modern)
            box.toggled.connect(lambda _on: self._count())
            self.checks[team] = box
            grid.addWidget(box, index % 8, index // 8)
        layout.addLayout(grid)
        row = QHBoxLayout()
        self.all_button = QPushButton("All 32")
        self.none_button = QPushButton("None")
        self.all_button.clicked.connect(lambda: self._set_all(True))
        self.none_button.clicked.connect(lambda: self._set_all(False))
        self.count_label = QLabel("")
        row.addWidget(self.all_button)
        row.addWidget(self.none_button)
        row.addWidget(self.count_label, 1)
        layout.addLayout(row)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Ok).setText("Use these books")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self._count()

    def _set_all(self, on: bool) -> None:
        for box in self.checks.values():
            box.setChecked(on)

    def _count(self) -> None:
        picked = len(self.selected_teams())
        self.count_label.setText(f"Modern {picked}, Classic {len(self.checks) - picked}")

    def selected_teams(self) -> tuple[str, ...]:
        return tuple(team for team, box in self.checks.items() if box.isChecked())


def choose_pack_to_open(parent: QWidget | None = None, directory: str = "") -> Path | None:
    name, _filter = QFileDialog.getOpenFileName(
        parent, "Open a playbook pack", directory,
        f"Playbook packs (*{pack_mod.PACK_EXTENSION});;All files (*)",
    )
    return Path(name) if name else None


def choose_pack_to_save(parent: QWidget | None = None, suggested: str = "") -> Path | None:
    name, _filter = QFileDialog.getSaveFileName(
        parent, "Export a playbook pack", suggested,
        f"Playbook packs (*{pack_mod.PACK_EXTENSION})",
    )
    if not name:
        return None
    path = Path(name)
    return path if path.suffix.casefold() == pack_mod.PACK_EXTENSION else path.with_suffix(
        pack_mod.PACK_EXTENSION
    )


__all__ = [
    "BOOK_SET_EXPLAINER", "BOOK_SET_TEAM_NAMES", "BookSetTeamsDialog", "book_set_status_text",
    "ENGINE_LIMITS_TEXT", "PLAN_COLUMNS", "PlaybookPackExportDialog",
    "PlaybookPackInstallDialog", "budget_bars", "choose_pack_to_open", "choose_pack_to_save",
    "install_blockers", "pack_summary_lines", "plan_table_rows", "team_choices",
]
