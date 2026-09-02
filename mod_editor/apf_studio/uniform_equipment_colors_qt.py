"""All-team HOME/AWAY facemask and Team-turtleneck selector controls."""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Callable

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

_TOOLS = str(Path(__file__).resolve().parents[2] / "tools")
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)
import apf_uniform_equipment_color_patch as equipment_colors  # noqa: E402


class _ColorBankEditor(QWidget):
    def __init__(self, label: str):
        super().__init__()
        self.label = label
        self._palette: tuple[int, ...] = (0,) * 10
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        note = QLabel(
            f"{label} uses its own ten-color uniform palette. These controls "
            "change only the verified selector index; palette colors and metadata stay unchanged."
        )
        note.setObjectName("metadataText")
        note.setWordWrap(True)
        outer.addWidget(note)
        grid = QGridLayout()
        self.facemask = QComboBox()
        self.facemask.setAccessibleName(f"{label} facemask palette color")
        self.facemask_swatch = self._swatch()
        self.turtleneck = QComboBox()
        self.turtleneck.setAccessibleName(f"{label} Team-turtleneck palette color")
        self.turtleneck_swatch = self._swatch()
        grid.addWidget(QLabel("Facemask bar"), 0, 0)
        grid.addWidget(self.facemask_swatch, 0, 1)
        grid.addWidget(self.facemask, 0, 2)
        grid.addWidget(QLabel("Team turtleneck"), 1, 0)
        grid.addWidget(self.turtleneck_swatch, 1, 1)
        grid.addWidget(self.turtleneck, 1, 2)
        grid.setColumnStretch(2, 1)
        outer.addLayout(grid)
        self.facemask.currentIndexChanged.connect(self._update_swatches)
        self.turtleneck.currentIndexChanged.connect(self._update_swatches)

    @staticmethod
    def _swatch() -> QLabel:
        swatch = QLabel(" ")
        swatch.setFixedSize(30, 22)
        swatch.setFrameShape(QFrame.Box)
        return swatch

    @staticmethod
    def _name(index: int) -> str:
        if index == 0:
            return "White / silver"
        if index == 1:
            return "Black"
        return f"Color {index - 1}"

    def set_palette(self, palette: tuple[int, ...]) -> None:
        if len(palette) != 10:
            raise ValueError("Uniform equipment palette must contain ten colors")
        self._palette = tuple(palette)
        current = (self.facemask.currentData(), self.turtleneck.currentData())
        for combo in (self.facemask, self.turtleneck):
            combo.blockSignals(True)
            combo.clear()
            for index, argb in enumerate(self._palette):
                combo.addItem(
                    f"{index} · {self._name(index)} · #{argb & 0xFFFFFF:06X}",
                    index,
                )
            combo.blockSignals(False)
        for combo, previous in zip(
            (self.facemask, self.turtleneck), current, strict=True
        ):
            found = combo.findData(previous)
            if found >= 0:
                combo.setCurrentIndex(found)
        self._update_swatches()

    def set_bank(self, bank: equipment_colors.EquipmentColorBank) -> None:
        self.facemask.setCurrentIndex(bank.facemask_palette_index)
        self.turtleneck.setCurrentIndex(bank.team_turtleneck_palette_index)
        self._update_swatches()

    def bank(self) -> equipment_colors.EquipmentColorBank:
        return equipment_colors.EquipmentColorBank(
            int(self.facemask.currentData()), int(self.turtleneck.currentData())
        )

    def _update_swatches(self) -> None:
        for combo, swatch in (
            (self.facemask, self.facemask_swatch),
            (self.turtleneck, self.turtleneck_swatch),
        ):
            index = combo.currentData()
            if type(index) is int and 0 <= index < len(self._palette):
                color = self._palette[index] & 0xFFFFFF
                swatch.setStyleSheet(
                    f"background: #{color:06X}; border: 1px solid #8795aa;"
                )


class UniformEquipmentColorsPanel(QFrame):
    """Project-backed exact selector editor for every game team."""

    modifiedChanged = pyqtSignal()

    def __init__(self, facade, run_task: Callable):
        super().__init__()
        self.facade = facade
        self.run_task = run_task
        self.setObjectName("panel")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 13, 14, 13)
        outer.setSpacing(9)
        title = QLabel("Uniform Equipment Colors · all 40 teams")
        title.setObjectName("panelTitle")
        description = QLabel(
            "Per-uniform-set colors (not global): pick a team slot, then set HOME "
            "and AWAY independently for the facemask bar and Team turtleneck. "
            "HOME facemask ≠ AWAY for the same team. Visor type (None / Clear / "
            "Dark) is edited per-player in Rosters → Save Players — this panel "
            "does not own a per-uniform visor-tint field."
        )
        description.setObjectName("cardBody")
        description.setWordWrap(True)
        outer.addWidget(title)
        outer.addWidget(description)

        team_row = QHBoxLayout()
        team_row.addWidget(QLabel("Team:"))
        self.team_filter = QLineEdit()
        self.team_filter.setPlaceholderText("Filter teams… (e.g. Sharks, Cobras)")
        self.team_filter.setClearButtonEnabled(True)
        self.team_filter.setAccessibleName("Filter equipment-color teams")
        self.team_filter.setProperty("studioSearch", True)
        self.team_filter.setToolTip(
            "Type to filter the 40 APF team slots (fictional names, not NFL "
            "city labels). HOME/AWAY facemask and turtleneck stay independent per team."
        )
        self.team = QComboBox()
        self.team.setAccessibleName("Uniform equipment-color team")
        self._all_team_items: list[tuple[int, str]] = []
        for team_index in range(equipment_colors.TEAM_COUNT):
            label = equipment_colors.team_label(team_index)
            self._all_team_items.append((team_index, label))
            self.team.addItem(label, team_index)
        team_row.addWidget(self.team_filter, 1)
        team_row.addWidget(self.team, 2)
        outer.addLayout(team_row)

        self.banks = QTabWidget()
        self.home = _ColorBankEditor("HOME")
        self.away = _ColorBankEditor("AWAY")
        self.banks.addTab(self.home, "HOME kit only")
        self.banks.addTab(self.away, "AWAY kit only")
        outer.addWidget(self.banks)

        boundary = QLabel(
            "Exact write boundary: facemask selector slot 3 byte 6 and "
            "turtleneck selector slot 0 byte 2. Values are palette indices 0–9."
        )
        boundary.setObjectName("findingText")
        boundary.setWordWrap(True)
        outer.addWidget(boundary)

        actions = QHBoxLayout()
        self.stage_button = QPushButton("Stage equipment colors")
        self.stage_button.setObjectName("secondaryButton")
        self.revert_button = QPushButton("Revert staged colors")
        self.revert_button.setObjectName("dangerQuietButton")
        actions.addWidget(self.stage_button)
        actions.addWidget(self.revert_button)
        actions.addStretch(1)
        outer.addLayout(actions)
        self.status = QLabel("Load your game to read uniform equipment colors.")
        self.status.setObjectName("metadataText")
        self.status.setWordWrap(True)
        outer.addWidget(self.status)

        self.team.currentIndexChanged.connect(self.set_context)
        self.team_filter.textChanged.connect(self._filter_teams)
        self.stage_button.clicked.connect(self._stage)
        self.revert_button.clicked.connect(self._revert)
        self.set_context()

    def _filter_teams(self, needle: str) -> None:
        """Filter the team combo without changing staged colors mid-type."""

        needle_cf = needle.strip().casefold()
        current = self.team.currentData()
        self.team.blockSignals(True)
        self.team.clear()
        for team_index, label in self._all_team_items:
            if needle_cf and needle_cf not in label.casefold():
                continue
            self.team.addItem(label, team_index)
        self.team.blockSignals(False)
        if self.team.count() == 0:
            self.status.setText(
                "No teams match that filter. Clear the filter box to see all 40."
            )
            return
        found = self.team.findData(current)
        self.team.setCurrentIndex(found if found >= 0 else 0)
        self.set_context()

    def _team_index(self) -> int:
        data = self.team.currentData()
        if data is None:
            raise RuntimeError("No team selected — clear the team filter.")
        return int(data)

    def _value(self) -> equipment_colors.UniformEquipmentColors:
        return equipment_colors.validate_colors(
            equipment_colors.UniformEquipmentColors(
                self._team_index(), self.home.bank(), self.away.bank()
            )
        )

    def set_context(self) -> None:
        ready = bool(self.facade.source_ready)
        has_team = self.team.count() > 0 and self.team.currentData() is not None
        # Keep Stage clickable when blocked so it is never a silent gray button —
        # click / tooltip explain the next step (Load game / clear filter).
        self.team.setEnabled(ready)
        self.banks.setEnabled(ready and has_team)
        self.stage_button.setEnabled(True)
        # Never silent-gray: Stage and Revert stay clickable; disableReason explains.
        self.revert_button.setEnabled(True)
        if not ready:
            reason = "Load your APF game (0A / extracted folder / ISO) first."
            self.stage_button.setToolTip(reason)
            self.stage_button.setProperty("disableReason", reason)
            self.revert_button.setToolTip(reason)
            self.revert_button.setProperty("disableReason", reason)
            self.status.setText("Load your game to read uniform equipment colors.")
            return
        if not has_team:
            reason = "No teams match that filter. Clear the filter box to see all 40."
            self.stage_button.setToolTip(reason)
            self.stage_button.setProperty("disableReason", reason)
            self.revert_button.setToolTip(reason)
            self.revert_button.setProperty("disableReason", reason)
            self.status.setText(reason)
            return
        try:
            inspection = self.facade.uniform_equipment_color_inspection(
                self._team_index()
            )
            value = self.facade.uniform_equipment_color_value(self._team_index())
        except Exception as exc:
            # Inline status only — never a blocking popup on team select.
            reason = (
                f"Could not read uniform equipment colors: {exc}. "
                "Nothing was staged. Pick another team or reload your game."
            )
            self.status.setText(reason)
            self.stage_button.setToolTip(reason)
            self.stage_button.setProperty("disableReason", reason)
            self.revert_button.setToolTip(reason)
            self.revert_button.setProperty("disableReason", reason)
            return
        self.home.set_palette(inspection.home_palette)
        self.away.set_palette(inspection.away_palette)
        self.home.set_bank(value.home)
        self.away.set_bank(value.away)
        target_id = equipment_colors.asset_id(value.team_index)
        modified = target_id in self.facade.modified_asset_ids
        revert_tip = (
            "Remove staged equipment colors for this team from the project."
            if modified
            else "Nothing to revert—equipment colors for this team are still original."
        )
        self.revert_button.setToolTip(revert_tip)
        self.revert_button.setProperty(
            "disableReason", "" if modified else revert_tip
        )
        self.stage_button.setToolTip(
            "Stage HOME/AWAY facemask + turtleneck bank picks for this team only "
            "(per kit). Player visors stay under Rosters → Save Players."
        )
        self.stage_button.setProperty("disableReason", "")
        self.status.setText(
            ("● Staged in this project. " if modified else "○ Source values (read-only). ")
            + "Build preserves both palettes and every nonselected selector byte."
        )

    def _stage(self) -> None:
        reason = str(self.stage_button.property("disableReason") or "").strip()
        if reason:
            self.status.setText(reason)
            return
        if not self.facade.source_ready:
            self.status.setText(
                "Load your APF game (0A / extracted folder / ISO) first."
            )
            return
        try:
            value = self._value()
        except Exception as exc:
            self.status.setText(str(exc))
            return
        self.run_task(
            "Staging uniform equipment colors",
            lambda progress: self.facade.replace_uniform_equipment_colors(
                value, progress
            ),
            lambda _result: self._mutation_complete(),
            True,
        )

    def _revert(self) -> None:
        reason = str(self.revert_button.property("disableReason") or "").strip()
        if reason:
            self.status.setText(reason)
            return
        target_id = equipment_colors.asset_id(self._team_index())
        self.run_task(
            "Reverting uniform equipment colors",
            lambda progress: self.facade.revert(target_id, progress),
            lambda _result: self._mutation_complete(),
            True,
        )

    def _mutation_complete(self) -> None:
        self.set_context()
        self.modifiedChanged.emit()


__all__ = ["UniformEquipmentColorsPanel"]
