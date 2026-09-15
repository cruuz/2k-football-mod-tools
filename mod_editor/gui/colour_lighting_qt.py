"""Project colour controls. Pure preview and settings; the core owner does all writes."""
from copy import deepcopy

from PyQt5.QtCore import Qt, QSignalBlocker, pyqtSignal
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
                             QPushButton, QCheckBox, QComboBox, QSlider, QDoubleSpinBox,
                             QTabWidget, QStackedWidget)
from mod_editor.core import nfl2k5_modern_color as colour


class ColourLightingControls(QWidget):
    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._settings = colour.default_settings()
        self.rows, self.groups, self.links = {}, {}, {}
        root = QVBoxLayout(self)
        title = QLabel("Colour & lighting")
        root.addWidget(title)
        buttons = QHBoxLayout()
        self.broadcast_button = QPushButton("Broadcast (default)")
        self.retail_button = QPushButton("Retail")
        buttons.addWidget(self.broadcast_button)
        buttons.addWidget(self.retail_button)
        buttons.addStretch()
        root.addLayout(buttons)
        self.broadcast_button.clicked.connect(lambda: self.reset(False))
        self.retail_button.clicked.connect(lambda: self.reset(True))
        self.state_label = QLabel()
        self.state_label.setWordWrap(True)
        root.addWidget(self.state_label)
        selectors = QHBoxLayout()
        self.class_combo, self.rig_combo = QComboBox(), QComboBox()
        self.class_combo.setAccessibleName("Preview stadium class")
        self.rig_combo.setAccessibleName("Preview light condition")
        for key, ref in colour.PREVIEW_CLASSES.items():
            self.class_combo.addItem(ref["label"], key)
        for key, label in colour.RIG_LABELS.items():
            self.rig_combo.addItem(label, key)
        selectors.addWidget(QLabel("Stadium class"))
        selectors.addWidget(self.class_combo)
        selectors.addWidget(QLabel("Condition"))
        selectors.addWidget(self.rig_combo)
        root.addLayout(selectors)
        self.model_note = QLabel(colour.preview()["scope"])
        self.model_note.setWordWrap(True)
        root.addWidget(self.model_note)
        self.tabs = QTabWidget()
        root.addWidget(self.tabs)
        for group in ("turf", "endzones", "outside"):
            self.tabs.addTab(self._group(group), colour.GROUPS[group])
        detail = QWidget()
        details = QVBoxLayout(detail)
        for group in ("divots", "normal", "tints"):
            details.addWidget(self._group(group))
        self.tabs.addTab(detail, "Detail & tints")
        lights = QWidget()
        light_layout = QVBoxLayout(lights)
        light_layout.addWidget(QLabel("Uses the selected condition above. Night and dome share the retail table.\n"
                                      "Directions and light counts remain retail. Day/afternoon colour recipe also sets shadow strength."))
        self.light_stack = QStackedWidget()
        for name in colour.RIG_LABELS:
            self.light_stack.addWidget(self._group("rig_" + name))
        light_layout.addWidget(self.light_stack)
        self.tabs.addTab(lights, "Light rigs")
        self.class_combo.currentIndexChanged.connect(self._selection)
        self.rig_combo.currentIndexChanged.connect(self._selection)
        self.set_settings(self._settings)
        self.set_active(False)

    def _group(self, group):
        page = QWidget()
        layout = QGridLayout(page)
        layout.setAlignment(Qt.AlignTop)
        toggle = QCheckBox("Adjust " + colour.GROUPS[group].lower())
        toggle.setObjectName("colour_group_" + group)
        self.groups[group] = toggle
        layout.addWidget(toggle, 0, 0, 1, 3)
        toggle.toggled.connect(lambda on, g=group: self._group_changed(g, on))
        if group in ("endzones", "outside"):
            link = QCheckBox("Follow turf colour")
            self.links[group] = link
            layout.addWidget(link, 1, 0, 1, 3)
            link.toggled.connect(lambda on, g=group: self._link_changed(g, on))
        layout.addWidget(QLabel("PREDICTED turf"), 1, 3)
        layout.addWidget(QLabel("Broadcast target"), 1, 4)
        n = 2
        for key, spec in colour.control_specs().items():
            if spec["group"] != group:
                continue
            use = QCheckBox(spec["label"])
            use.setObjectName("colour_use_" + key)
            use.setToolTip("On uses the saved value. Off uses this lever's retail value; your saved value is retained.")
            slider, spin = QSlider(Qt.Horizontal), QDoubleSpinBox()
            steps = round((spec["maximum"] - spec["minimum"]) / spec["step"])
            slider.setRange(0, steps)
            slider.setMinimumWidth(100)
            spin.setDecimals(3)
            spin.setRange(spec["minimum"], spec["maximum"])
            spin.setSingleStep(spec["step"])
            spin.setKeyboardTracking(False)
            for w in (slider, spin):
                w.setAccessibleName(colour.GROUPS[group] + ": " + spec["label"])
            prediction, target = QLabel(), QLabel()
            for label in (prediction, target):
                label.setMinimumWidth(108)
                label.setAlignment(Qt.AlignCenter)
            self.rows[key] = dict(use=use, slider=slider, spin=spin, prediction=prediction, target=target)
            for col, widget in enumerate((use, slider, spin, prediction, target)):
                layout.addWidget(widget, n, col)
            use.toggled.connect(lambda on, k=key: self._use_changed(k, on))
            slider.valueChanged.connect(lambda v, k=key: self._number_changed(k, v, True))
            spin.valueChanged.connect(lambda v, k=key: self._number_changed(k, v, False))
            n += 1
        if group == "turf":
            note = QLabel("Map contrast scales existing green value differences, including stripes already in a colour map.\n"
                          "It cannot add stripes. Material-only turf has no map contrast control.")
            note.setWordWrap(True)
            layout.addWidget(note, n, 0, 1, 5)
        layout.setColumnStretch(1, 1)
        return page

    def settings(self):
        return deepcopy(self._settings)

    def set_settings(self, settings):
        self._settings = colour.normalize_settings(settings)
        blockers = [QSignalBlocker(w) for w in self.findChildren(QWidget)]
        for group, widget in self.groups.items():
            widget.setChecked(self._settings["enabled"][group])
        for group, widget in self.links.items():
            widget.setChecked(self._settings["linked"][group])
        for key, row in self.rows.items():
            spec = colour.control_specs()[key]
            value = self._settings["values"][key]
            row["use"].setChecked(key not in self._settings["disabled"])
            row["spin"].setValue(value)
            row["slider"].setValue(round((value - spec["minimum"]) / spec["step"]))
        self.class_combo.setCurrentIndex(self.class_combo.findData(self._settings["preview_class"]))
        self.rig_combo.setCurrentIndex(self.rig_combo.findData(self._settings["preview_rig"]))
        del blockers
        self._refresh()

    def reset(self, retail=False):
        self.set_settings(colour.default_settings(retail=retail))
        self.changed.emit()

    def set_active(self, enabled):
        self.state_label.setText(("Included in this build. " if enabled else "Option is Off. These are previews of stored settings; enable the option above to build them. ") +
                                "Changes stay with this project. To change or reset a grade already baked into a disc, use the original retail source.")

    def _number_changed(self, key, value, from_slider):
        spec = colour.control_specs()[key]
        if from_slider:
            value = round(spec["minimum"] + value * spec["step"], 6)
        self._settings["values"][key] = float(value)
        row = self.rows[key]
        other = row["spin"] if from_slider else row["slider"]
        blocker = QSignalBlocker(other)
        other.setValue(value if from_slider else round((value - spec["minimum"]) / spec["step"]))
        del blocker
        self._refresh()
        self.changed.emit()

    def _group_changed(self, group, enabled):
        self._settings["enabled"][group] = enabled
        self._refresh()
        self.changed.emit()

    def _link_changed(self, group, linked):
        self._settings["linked"][group] = linked
        self._refresh()
        self.changed.emit()

    def _use_changed(self, key, enabled):
        disabled = set(self._settings["disabled"])
        disabled.discard(key) if enabled else disabled.add(key)
        self._settings["disabled"] = sorted(disabled)
        self._refresh()
        self.changed.emit()

    def _selection(self):
        self._settings["preview_class"] = self.class_combo.currentData()
        self._settings["preview_rig"] = self.rig_combo.currentData()
        self._refresh()
        self.changed.emit()

    @staticmethod
    def _swatch(widget, rgb):
        text = "#%02x%02x%02x" % rgb
        ink = "white" if sum(rgb) < 390 else "black"
        widget.setStyleSheet(f"QLabel {{ background: {text}; color: {ink}; padding: 4px; border: 1px solid #777; }}")
        widget.setText(", ".join(map(str, rgb)))

    def _refresh(self):
        estimate = colour.preview(self._settings)
        if hasattr(self, "light_stack"):
            self.light_stack.setCurrentIndex(list(colour.RIG_LABELS).index(self._settings["preview_rig"]))
        for key, row in self.rows.items():
            group = colour.control_specs()[key]["group"]
            linked = group in self.links and self._settings["linked"][group] and key.split(".")[1] not in ("match", "falloff")
            available = self._settings["enabled"][group] and not linked
            if key == "turf.map_contrast":
                available = available and estimate["map"]
            row["use"].setEnabled(available)
            for w in (row["slider"], row["spin"]):
                w.setEnabled(available and key not in self._settings["disabled"])
            self._swatch(row["prediction"], estimate["predicted"])
            self._swatch(row["target"], estimate["target"])
            row["prediction"].setToolTip(estimate["scope"] + " Reference: " + estimate["source"])
