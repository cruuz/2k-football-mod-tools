"""Independent global-threshold editor; no situation-table ownership."""
from pathlib import Path
import tempfile

from PyQt5.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
                               QFileDialog, QFormLayout, QHBoxLayout, QLabel, QMessageBox,
                               QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout)
from mod_editor.core import apf2k8_fourth_down as model


class FourthDownDialog(QDialog):
    def __init__(self, launcher, parent=None):
        super().__init__(parent)
        self.launcher = launcher
        self.setWindowTitle('CPU fourth-down triggers')
        self.resize(820, 740)
        root = QVBoxLayout(self)
        note = QLabel('Global settings for every CPU book. EXPERIMENTAL; off by default. '
                      'These change the kick decision and draw-offside gates. In-game behavior is UNWITNESSED.')
        note.setWordWrap(True); root.addWidget(note)
        form = QFormLayout(); root.addLayout(form)
        self.profile = QComboBox()
        self.profile.addItem('Retail BASE', model.PROFILES[0])
        self.profile.addItem('Title Update 1.1', model.PROFILES[1])
        form.addRow('Executable profile', self.profile)
        self.fields = {}
        for name, title, retail, low, high, step, help_text in model.FIELDS:
            widget = QDoubleSpinBox()
            widget.setDecimals(2); widget.setRange(low, high); widget.setSingleStep(step)
            widget.setValue(retail); widget.setToolTip(help_text + f' Retail: {retail:g}.')
            widget.setAccessibleName(title)
            self.fields[name] = widget
            form.addRow(title, widget)
            widget.valueChanged.connect(self.refresh_preview)
        self.enabled = QCheckBox('Enable this experimental patch')
        self.enabled.setChecked(False); root.addWidget(self.enabled)
        preview_note = QLabel('Preview: 4th and 1, first period, tied score, neutral urgency, '
                              '50-yard kicker range and cached random value 0.5. '
                              'Late-game gates and real kicker skills can change the choice. '
                              'The draw still requires three timeouts and its other retail gates.')
        preview_note.setWordWrap(True); root.addWidget(preview_note)
        self.preview = QTableWidget(5, 3)
        self.preview.setHorizontalHeaderLabels(['Distance to goal', 'Retail decision', 'Edited decision'])
        self.preview.setEditTriggers(QTableWidget.NoEditTriggers)
        self.preview.horizontalHeader().setStretchLastSection(True)
        root.addWidget(self.preview)
        row = QHBoxLayout(); root.addLayout(row)
        reset = QPushButton('Retail defaults'); reset.clicked.connect(self.reset_defaults); row.addWidget(reset)
        export = QPushButton('Export patch…'); export.clicked.connect(self.export); row.addWidget(export)
        self.install_button = QPushButton('Review and install…'); self.install_button.clicked.connect(self.install)
        row.addWidget(self.install_button)
        remove = QPushButton('Remove patch'); remove.clicked.connect(self.remove); row.addWidget(remove)
        self.status = QLabel(); self.status.setWordWrap(True); root.addWidget(self.status)
        close = QDialogButtonBox(QDialogButtonBox.Close); close.rejected.connect(self.reject); root.addWidget(close)
        self.enabled.toggled.connect(self.install_button.setEnabled)
        self.install_button.setEnabled(False)
        self.load_installed()
        self.refresh_preview(); self.refresh_status()

    def document(self):
        return model.PatchDocument(self.profile.currentData(),
                                   model.Thresholds(**{k: v.value() for k, v in self.fields.items()}),
                                   self.enabled.isChecked())

    def load_installed(self):
        if self.launcher.settings.xenia_path is None:
            return
        path = self.launcher.settings.patches_folder / model.FILENAME
        if not path.is_file() or path.is_symlink():
            return
        try:
            doc = model.parse_payload(path.read_bytes())
            self.profile.setCurrentIndex(model.PROFILES.index(doc.profile))
            for name, widget in self.fields.items():
                widget.setValue(getattr(doc.thresholds, name))
            self.enabled.setChecked(doc.enabled)
        except (OSError, ValueError, model.ValidationError):
            pass  # refresh_status presents the existing installer diagnostic inline

    def reset_defaults(self):
        for name, _, retail, *_ in model.FIELDS:
            self.fields[name].setValue(retail)
        self.enabled.setChecked(False)

    def refresh_preview(self):
        if not hasattr(self, 'preview'):
            return
        for i, goal in enumerate((30, 45, 50, 52, 70)):
            values = (f'{goal} yards', model.preview(goal_yards=goal),
                      model.preview(self.document().thresholds, goal_yards=goal))
            for j, value in enumerate(values):
                self.preview.setItem(i, j, QTableWidgetItem(value))

    def refresh_status(self):
        self.status.setText(self.launcher.pass_fetch_status(kind='fourth_down')['message'])

    def export(self):
        path, _ = QFileDialog.getSaveFileName(self, 'Export CPU fourth-down patch', model.FILENAME,
                                             'Xenia patch (*.patch.toml)')
        if not path:
            return
        try:
            model.write_patch(self.document(), Path(path))
            self.status.setText(f'Patch exported to {path}. Install it to use it in Studio launches. Gameplay UNWITNESSED.')
        except (OSError, ValueError, model.ValidationError) as exc:
            self.status.setText(str(exc))

    def install(self):
        if not self.enabled.isChecked():
            return
        if not self.launcher.settings.configured:
            self.status.setText('Configure Xenia Edge or Canary in the Studio first, then install the patch.')
            return
        answer = QMessageBox.question(self, 'Install global fourth-down patch?',
            'Install the reviewed thresholds for every CPU book and enable Xenia patches? '
            'This also activates other installed patches marked enabled. Restart Xenia after changing patches. '
            'The in-game result is UNWITNESSED.', QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer != QMessageBox.Yes:
            return
        try:
            with tempfile.TemporaryDirectory(prefix='apf-fourth-down-') as temporary:
                source = Path(temporary) / model.FILENAME
                model.write_patch(self.document(), source)
                self.launcher.install_pass_fetch_patch(source, kind='fourth_down', consent=True)
            self.refresh_status()
        except (OSError, ValueError, model.ValidationError) as exc:
            self.status.setText(str(exc))

    def remove(self):
        try:
            self.launcher.remove_pass_fetch_patch(kind='fourth_down')
            self.enabled.setChecked(False)
            self.refresh_status()
        except (OSError, ValueError, model.ValidationError) as exc:
            self.status.setText(str(exc))
