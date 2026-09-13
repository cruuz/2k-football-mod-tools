#!/usr/bin/env python3
"""Small stadium climate editor; writes a plan, never the selected game source."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (QApplication, QComboBox, QDialog, QDoubleSpinBox,
                               QFileDialog, QFormLayout, QHBoxLayout, QLabel,
                               QPushButton, QVBoxLayout)
from mod_editor.core import nfl2k5_weather as weather


class WeatherDialog(QDialog):
    saved = pyqtSignal(str)

    def __init__(self, source, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Weather editor (experimental)")
        self.resize(680, 440)
        self.source = Path(source)
        self.draft = None
        self._loading = False
        layout = QVBoxLayout(self)
        intro = QLabel(
            "EXPERIMENTAL / UNWITNESSED. Edit the disc's stadium climate and save a build plan. "
            "Test with a new franchise; adoption by existing saves is unproved. "
            "Rain or snow follows temperature, so they have one shared precipitation chance. "
            "July and August share a slot; March through June have no supported slot. "
            "Wind is a baseline, and the game varies it. Indoor weather is suppressed.")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        form = QFormLayout()
        layout.addLayout(form)
        self.stadium = QComboBox()
        self.stadium.setAccessibleName("Stadium and city")
        self.month = QComboBox()
        self.month.setAccessibleName("Climate month")
        for month, name in zip(weather.MONTHS, ("July / August", "September", "October", "November",
                                               "December", "January", "February")):
            self.month.addItem(name, month)
        form.addRow("Stadium / city", self.stadium)
        form.addRow("Month", self.month)
        self.fields = {}
        for field, label, suffix in (("temperature_f", "Temperature baseline", " °F"),
                                     ("precipitation_pct", "Precipitation chance", " %"),
                                     ("wind_mph", "Wind baseline", " mph")):
            box = QDoubleSpinBox()
            box.setRange(*weather.FIELDS[field][1:])
            box.setDecimals(3)
            box.setSuffix(suffix)
            box.setAccessibleName(label)
            form.addRow(label, box)
            box.valueChanged.connect(lambda value, field=field: self._edit(field, value))
            self.fields[field] = box
        buttons = QHBoxLayout()
        layout.addLayout(buttons)
        self.preset_button = QPushButton("Milder outdoor climate (+2 °F, authored)")
        self.preset_button.setToolTip("A sensitivity example for the retail NFL home rows, not measured modern climate data. One Undo restores the prior draft.")
        self.undo_button = QPushButton("Undo")
        self.save_button = QPushButton("Save build edits…")
        for button in (self.preset_button, self.undo_button, self.save_button):
            buttons.addWidget(button)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.stadium.currentIndexChanged.connect(self._show_values)
        self.month.currentIndexChanged.connect(self._show_values)
        self.preset_button.clicked.connect(self._preset)
        self.undo_button.clicked.connect(self._undo)
        self.save_button.clicked.connect(self._save)
        try:
            self.draft = weather.WeatherDraft(weather.load_resource(self.source))
            self.stadium.blockSignals(True)
            for row in self.draft.catalog["rows"]:
                roof = " (indoor)" if row["indoor"] else ""
                self.stadium.addItem(f"{row['stadium']} / {row['city']}{roof}", row["index"])
            self.stadium.blockSignals(False)
            self._show_values()
        except (OSError, ValueError) as exc:
            self.status.setText(f"Cannot open this climate table: {exc}. Choose a supported USA disc or extracted game folder.")
            for widget in (self.stadium, self.month, *self.fields.values(), self.preset_button,
                           self.undo_button, self.save_button):
                widget.setEnabled(False)

    def _show_values(self, *_):
        if self.draft is None or self.stadium.currentData() is None:
            return
        index, month = self.stadium.currentData(), self.month.currentData()
        values = dict(self.draft.catalog["rows"][index]["months"][weather.MONTH_TO_SLOT[month]])
        plan = self.draft.plan()
        for change in plan["changes"]:
            if change["stadium_index"] == index and change["month"] == month:
                values[change["field"]] = change["after"]
        self._loading = True
        try:
            for field, box in self.fields.items():
                box.setValue(values[field])
        finally:
            self._loading = False
        self.save_button.setEnabled(bool(plan["changes"]))
        self.status.setText(f"{len(plan['changes'])} staged fields. Save build edits to use these values in Build. The source has not been changed.")

    def _edit(self, field, value):
        if self.draft is None or self._loading:
            return
        self.draft.set_value(self.stadium.currentData(), self.month.currentData(), field, value)
        self.save_button.setEnabled(bool(self.draft.plan()["changes"]))
        self.status.setText(f"{len(self.draft.plan()['changes'])} staged fields. Save build edits to use these values in Build.")

    def _preset(self):
        self.draft.milder_outdoor_preset()
        self._show_values()

    def _undo(self):
        self.draft.undo()
        self._show_values()

    def save_plan(self, destination):
        """Same validated transaction used by the dialog and offscreen tests."""
        destination = Path(destination)
        weather.require(destination.suffix.lower() == ".json" and destination.resolve() != self.source.resolve(),
                        "Choose a separate .json file for the build edits")
        plan = self.draft.plan()
        weather.require(bool(plan["changes"]), "Change at least one climate field before saving")
        weather.apply(self.draft.resource, plan)
        weather.write_json(destination, plan)
        weather.require(weather.read_json(destination) == plan, "Saved climate plan did not read back; save it again")
        self.status.setText(f"Saved {len(plan['changes'])} climate edits to {destination.name}. EXPERIMENTAL / UNWITNESSED.")
        self.saved.emit(str(destination))

    def _save(self):
        name, _ = QFileDialog.getSaveFileName(self, "Save weather build edits", "weather-edits.json", "Climate plan (*.json)")
        if name:
            try:
                self.save_plan(name)
            except (OSError, ValueError) as exc:
                self.status.setText(f"Climate edits were not saved: {exc}. Choose a writable .json file and try again.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    app = QApplication.instance() or QApplication(sys.argv[:1])
    dialog = WeatherDialog(args.source)
    return dialog.exec()


if __name__ == "__main__":
    raise SystemExit(main())
