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
    for team in available:
        if team == pack.book.team:
            continue
        choices.append((f"Retarget to {team}", team))
    if available:
        choices.append((f"All {len(available)} team books", pack_mod.ALL_TEAMS))
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


from PyQt5.QtCore import Qt  # noqa: E402
from PyQt5.QtWidgets import (  # noqa: E402
    QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
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
        limits = QLabel(ENGINE_LIMITS_TEXT)
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
            result = self.host.install_playbook_pack(self.pack, teams, _quiet)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Install Playbook Pack", str(exc))
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
    "ENGINE_LIMITS_TEXT", "PLAN_COLUMNS", "PlaybookPackExportDialog",
    "PlaybookPackInstallDialog", "budget_bars", "choose_pack_to_open", "choose_pack_to_save",
    "install_blockers", "pack_summary_lines", "plan_table_rows", "team_choices",
]
