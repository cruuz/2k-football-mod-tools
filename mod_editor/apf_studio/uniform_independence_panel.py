"""The panel that explains uniform sharing and offers to end it.

The underlying capability existed for a long time as a command-line writer and
was never offered in the app, so the problem it solves kept getting reported as
if it had no answer: paint a wing on one team's helmet and it turns up on
several others.

The panel is written for someone who has never heard the words "selector slot".
It leads with the consequence, not the mechanism, shows the real per-family
numbers rather than a vague promise, and states plainly what is and is not
proved before anyone spends an hour editing textures on the strength of it.
"""

from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import uniform_independence


class UniformIndependencePanel(QFrame):
    """Describe the sharing problem, then offer the one plan that fixes it."""

    def __init__(self, facade, run_task, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("panel")
        self.facade = facade
        self._run_task = run_task
        self._plan: uniform_independence.IndependencePlan | None = None

        box = QVBoxLayout(self)
        box.setContentsMargins(14, 13, 14, 13)
        box.setSpacing(8)

        title = QLabel("Give every team its own uniform")
        title.setObjectName("panelTitle")
        box.addWidget(title)

        self.headline = QLabel("")
        self.headline.setObjectName("mutedLabel")
        self.headline.setWordWrap(True)
        box.addWidget(self.headline)

        self.table = QTableWidget(0, 4)
        self.table.setObjectName("assetTable")
        self.table.setHorizontalHeaderLabels(
            ["Part", "Shared now", "After", "Teams that stop sharing"]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionMode(QTableWidget.NoSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.table.setMinimumHeight(220)
        box.addWidget(self.table, 1)

        who = QLabel("Who uses each helmet right now")
        who.setObjectName("panelTitle")
        box.addWidget(who)

        self.helmets = QTableWidget(0, 3)
        self.helmets.setObjectName("assetTable")
        self.helmets.setHorizontalHeaderLabels(
            ["Helmet", "Teams using it", "Who"]
        )
        self.helmets.verticalHeader().setVisible(False)
        self.helmets.setSelectionMode(QTableWidget.NoSelection)
        self.helmets.setEditTriggers(QTableWidget.NoEditTriggers)
        self.helmets.setAlternatingRowColors(True)
        header = self.helmets.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        self.helmets.setMinimumHeight(180)
        box.addWidget(self.helmets, 1)

        self.caveat = QLabel(
            "This writes a new copy of your 0A file and never changes the one "
            "you loaded. It only re-points which texture each team uses; no "
            "artwork is altered, so your helmets look exactly the same until "
            "you edit them. Tested offline only: it has not been confirmed on "
            "a real Xbox 360."
        )
        self.caveat.setObjectName("mutedLabel")
        self.caveat.setWordWrap(True)
        box.addWidget(self.caveat)

        actions = QHBoxLayout()
        actions.addStretch(1)
        self.apply_button = QPushButton("Give every team its own uniform…")
        self.apply_button.setObjectName("primaryButton")
        self.apply_button.setToolTip(
            "Creates a new 0A file with each team pointed at its own textures.\n"
            "Your loaded game is opened read-only and is not modified."
        )
        self.apply_button.clicked.connect(self._apply)
        actions.addWidget(self.apply_button)
        box.addLayout(actions)
        # Shell-driven ready flag (may differ from facade.source still attached).
        self._source_ready = bool(getattr(self.facade, "source_ready", False))

        self.refresh()

    def refresh(self) -> None:
        """Describe the plan. Needs no game loaded, so it can always show."""

        if not uniform_independence.plan_available():
            self.headline.setText(
                "The uniform assignment plan is not available in this build."
            )
            tip = (
                "Uniform independence plan is not available in this build. "
                "Click still explains — button stays clickable."
            )
            self.apply_button.setEnabled(True)
            self.apply_button.setToolTip(tip)
            self.apply_button.setProperty("disableReason", tip)
            return
        try:
            plan = uniform_independence.describe_plan()
        except uniform_independence.UniformIndependenceError as exc:
            self.headline.setText(str(exc))
            tip = f"{exc} Click still explains — button stays clickable."
            self.apply_button.setEnabled(True)
            self.apply_button.setToolTip(tip)
            self.apply_button.setProperty("disableReason", tip)
            return

        self._plan = plan
        self.headline.setText(plan.headline())
        rows = [row for row in plan.families if not row.already_independent]
        self.table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            values = (
                row.family,
                str(row.distinct_before),
                str(row.distinct_after),
                str(row.teams_changed),
            )
            for column, text in enumerate(values):
                item = QTableWidgetItem(text)
                if column:
                    item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(index, column, item)
        self._fill_helmet_usage(plan)
        source_ok = bool(self._source_ready and self._source_index() is not None)
        can = bool(rows) and source_ok
        if can:
            tip = (
                "Creates a new 0A file with each team pointed at its own textures.\n"
                "Your loaded game is opened read-only and is not modified."
            )
            block = ""
        elif not source_ok:
            tip = block = (
                "Load your APF game first. Independence writes a new 0A copy only. "
                "Click still explains — button stays clickable."
            )
        else:
            tip = block = (
                "All listed families are already independent — nothing to apply. "
                "Click still explains this."
            )
        self.apply_button.setEnabled(True)
        self.apply_button.setToolTip(tip)
        self.apply_button.setProperty("disableReason", block)

    def _fill_helmet_usage(self, plan: uniform_independence.IndependencePlan) -> None:
        """Name the teams behind each helmet, which is the reported surprise.

        A modder painting a wing for one team has no way to know from the app
        that fifteen other teams point at the same texture. Listing them turns
        that into something visible before the work rather than after it.
        """

        helmet = plan.helmet
        count = helmet.catalog_count if helmet is not None else 0
        rows = []
        for index in range(count):
            try:
                shared = uniform_independence.teams_using("helmet", index)
            except uniform_independence.UniformIndependenceError:
                return
            rows.append(shared)

        self.helmets.setRowCount(len(rows))
        for position, shared in enumerate(rows):
            if shared.teams:
                who = ", ".join(shared.teams)
            else:
                who = "unused - free to take over"
            values = (f"helmet {shared.asset_index:02d}", str(len(shared.teams)), who)
            for column, text in enumerate(values):
                item = QTableWidgetItem(text)
                if column == 1:
                    item.setTextAlignment(Qt.AlignCenter)
                item.setToolTip(shared.warning())
                self.helmets.setItem(position, column, item)

    def set_source_ready(self, ready: bool) -> None:
        self._source_ready = bool(ready)
        # Refresh tooltips/disableReason via refresh path when possible.
        if self._plan is not None or uniform_independence.plan_available():
            self.refresh()
            return
        tip = (
            "Load your APF game first. Independence writes a new 0A copy only."
            if not ready
            else "Uniform independence plan is not ready yet."
        )
        self.apply_button.setEnabled(True)
        self.apply_button.setToolTip(tip)
        self.apply_button.setProperty("disableReason", tip)

    def _source_index(self) -> Path | None:
        source = getattr(self.facade, "source", None)
        index = getattr(source, "index_0a", None)
        return index if isinstance(index, Path) else None

    def _apply(self) -> None:
        reason = str(self.apply_button.property("disableReason") or "").strip()
        if reason:
            from PyQt5.QtWidgets import QMessageBox

            QMessageBox.information(
                self,
                "Cannot apply uniform independence yet",
                reason
                + "\n\nFix: load APF with shared families remaining, then apply. "
                "Writes a new 0A — never mutates your original.",
            )
            return
        index = self._source_index()
        if index is None:
            QMessageBox.information(
                self,
                "Load your game first",
                "Open your APF 2K8 game before creating a new 0A file.",
            )
            return

        chosen, _filter = QFileDialog.getSaveFileName(
            self,
            "Save the new 0A file",
            str(Path.home() / "0A"),
            "APF volume (0A);;All files (*)",
        )
        if not chosen:
            return
        output = Path(chosen)
        manifest = output.with_name(output.name + "-manifest.json")

        plan = self._plan
        helmet = plan.helmet if plan is not None else None
        detail = (
            f"Helmets go from {helmet.distinct_before} shared textures to "
            f"{helmet.distinct_after}.\n\n" if helmet is not None else ""
        )
        confirm = QMessageBox(self)
        confirm.setWindowTitle("Create the new 0A file?")
        confirm.setIcon(QMessageBox.Question)
        confirm.setText(f"Write a new 0A to {output.parent}?")
        confirm.setInformativeText(
            detail
            + "Your loaded game is opened read-only and is not changed. Use the "
            "new file in place of your original 0A to get the result in game.\n\n"
            "This takes a few minutes."
        )
        go = confirm.addButton("Create it", QMessageBox.AcceptRole)
        confirm.addButton("Cancel", QMessageBox.RejectRole)
        confirm.exec_()
        if confirm.clickedButton() is not go:
            return

        def operation(progress):
            progress("Giving every team its own uniform", 0, 1)
            result = uniform_independence.apply_plan(index, output, manifest)
            progress("New 0A written", 1, 1)
            return result

        def done(result: object) -> None:
            changed = ""
            if isinstance(result, dict):
                recipe = result.get("recipe") or {}
                count = recipe.get("changed_team_family_assignment_count")
                if count is not None:
                    changed = f"{count} team assignments were changed.\n\n"
            box = QMessageBox(self)
            box.setWindowTitle("New 0A created")
            box.setIcon(QMessageBox.Information)
            box.setText(f"Saved to {output}")
            box.setInformativeText(
                changed
                + "Every team now points at its own textures, so editing one "
                "team's helmet no longer changes another's.\n\n"
                "Replace your game's 0A with this file, then load it here and "
                "edit helmets as usual."
            )
            box.addButton("Close", QMessageBox.RejectRole)
            box.exec_()

        self._run_task(
            "Giving every team its own uniform",
            operation,
            done,
            True,
        )
