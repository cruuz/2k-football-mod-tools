"""Field Art opacity controls; the scalar recipe is staged through the facade."""
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
                            QFormLayout, QCheckBox, QDoubleSpinBox, QPushButton)
from mod_editor.core.apf_field_material_writer import ENTRY_NAME_IDS, MATERIALS


class FieldMaterialOpacityPanel(QWidget):
    modifiedChanged = pyqtSignal()

    def __init__(self, facade, run_task):
        super().__init__()
        self.facade, self.run_task = facade, run_task
        self._source = None
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel('Field overlay opacity'))
        self.entry = QComboBox()
        for outer in ENTRY_NAME_IDS:
            self.entry.addItem(f'Field scene {outer}', outer)
        layout.addWidget(self.entry)
        self.controls = {}
        form = QFormLayout()
        for name in MATERIALS:
            row = QHBoxLayout()
            enabled = QCheckBox(name.replace('_', ' ').capitalize())
            value = QDoubleSpinBox()
            value.setRange(0, 100)
            value.setDecimals(2)
            value.setSuffix('%')
            value.setEnabled(False)
            enabled.toggled.connect(value.setEnabled)
            row.addWidget(enabled)
            row.addWidget(value)
            form.addRow(row)
            self.controls[name] = enabled, value
        layout.addLayout(form)
        self.note = QLabel('Select only the materials to change. Lower values make overlays more transparent. In-game appearance is unwitnessed.')
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        self.stage_button = QPushButton('Stage opacity changes')
        layout.addWidget(self.stage_button)
        self.stage_button.clicked.connect(self._stage)
        self.entry.currentIndexChanged.connect(self._load)
        self.setEnabled(False)

    def set_context(self):
        source = getattr(self.facade, 'source', None)
        self._source = source
        self.setEnabled(source is not None)
        if source is not None:
            self._load()

    def _load(self):
        if self._source is None: return
        outer, source = self.entry.currentData(), self._source
        self.stage_button.setEnabled(False)
        def done(result):
            if self._source is not source or self.entry.currentData() != outer: return
            materials, staged = result
            for material in materials:
                checkbox, value = self.controls[material.name]
                checkbox.setChecked(material.name in staged)
                value.setValue(staged.get(material.name, material.alpha) * 100)
            self.stage_button.setEnabled(True)
        self.run_task('Reading field opacity', lambda progress: self.facade.field_material_context(outer, progress), done, True)

    def _stage(self):
        values = {name: value.value() / 100 for name, (enabled, value) in self.controls.items() if enabled.isChecked()}
        if not values:
            self.note.setText('Tick at least one material to change its opacity.')
            return
        outer, source = self.entry.currentData(), self._source
        def done(report):
            if self._source is not source: return
            self.note.setText('Staged: ' + ', '.join(f"{c['material'].replace('_', ' ')} {c['before']:.0%} → {c['after']:.0%}" for c in report['changes'])
                             + '. Verified by reparse; in-game appearance is unwitnessed.')
            self.modifiedChanged.emit()
        self.run_task('Staging field opacity', lambda progress: self.facade.apply_field_material(outer, values, progress), done, True)
