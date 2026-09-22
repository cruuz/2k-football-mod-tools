"""APF charge-cap Build option and fourth-down-style Xenia patch transport."""
from dataclasses import replace
from pathlib import Path
import tempfile

from PyQt5.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                            QFileDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout)

from mod_editor.core import apf2k8_charge_abilities as model


class ChargeAbilitiesDialog(QDialog):
    def __init__(self, facade, parent=None):
        super().__init__(parent)
        self.facade, self.launcher = facade, facade.launcher
        self.setWindowTitle("Charged abilities")
        self.resize(640, 340)
        root = QVBoxLayout(self)
        note = QLabel("EXPERIMENTAL; gameplay UNWITNESSED. Charged abilities allow level 2 at any medal tier. "
                      "Players without one stop at level 1. QBs without Laser Arm or Rocket Arm still cannot charge in passing mode.")
        note.setWordWrap(True)
        root.addWidget(note)
        self.build_enabled = QCheckBox("Include ability-based charging patches in Build (EXPERIMENTAL)")
        self.build_enabled.setChecked(facade.build_options.charge_abilities)
        self.build_enabled.setToolTip("Off by default. Applies to this session's builds. Build exports BASE and TU 1.1 patches; install the matching profile below and restart Xenia.")
        self.build_enabled.toggled.connect(self.set_build_option)
        root.addWidget(self.build_enabled)
        self.profile = QComboBox()
        self.profile.addItem("Retail BASE", model.PROFILES[0])
        self.profile.addItem("Title Update 1.1", model.PROFILES[1])
        root.addWidget(self.profile)
        self.enabled = QCheckBox("Enable patch for export / install")
        self.enabled.setChecked(False)
        root.addWidget(self.enabled)
        row = QHBoxLayout()
        root.addLayout(row)
        export = QPushButton("Export patch…")
        export.clicked.connect(self.export)
        row.addWidget(export)
        self.install_button = QPushButton("Install enabled patch")
        self.install_button.clicked.connect(self.install)
        self.enabled.toggled.connect(self.install_button.setEnabled)
        self.install_button.setEnabled(False)
        row.addWidget(self.install_button)
        remove = QPushButton("Remove installed patch")
        remove.clicked.connect(self.remove)
        row.addWidget(remove)
        self.status = QLabel()
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        help_text = QLabel("Installing enables Xenia's patch setting, including other enabled patches. "
                          "Restart Xenia after installing or removing. Removing also clears this session's Build option; "
                          "the retail executable stays unchanged.")
        help_text.setWordWrap(True)
        root.addWidget(help_text)
        close = QDialogButtonBox(QDialogButtonBox.Close)
        close.rejected.connect(self.reject)
        root.addWidget(close)
        self.refresh_status()

    def set_build_option(self, enabled):
        self.facade.build_options = replace(self.facade.build_options, charge_abilities=enabled)

    def document(self):
        return model.PatchDocument(self.profile.currentData(), self.enabled.isChecked())

    def refresh_status(self):
        self.status.setText(self.launcher.pass_fetch_status(kind="charge_abilities")["message"])

    def export(self):
        name, _ = QFileDialog.getSaveFileName(self, "Export charged abilities patch", model.FILENAME,
                                             "Xenia patch (*.patch.toml)")
        if name:
            try:
                model.write_patch(self.document(), Path(name))
                self.status.setText("Patch exported. Install the matching profile and restart Xenia to apply it.")
            except (OSError, ValueError, model.ValidationError) as exc:
                self.status.setText(str(exc))

    def install(self):
        if not self.enabled.isChecked():
            return
        try:
            with tempfile.TemporaryDirectory(prefix="apf-charge-") as temporary:
                path = Path(temporary) / model.FILENAME
                model.write_patch(self.document(), path)
                self.launcher.install_pass_fetch_patch(path, kind="charge_abilities", consent=True)
            self.refresh_status()
        except (OSError, ValueError, model.ValidationError) as exc:
            self.status.setText(str(exc))

    def remove(self):
        try:
            self.launcher.remove_pass_fetch_patch(kind="charge_abilities")
            self.enabled.setChecked(False)
            self.build_enabled.setChecked(False)
            self.refresh_status()
        except (OSError, ValueError, model.ValidationError) as exc:
            self.status.setText(str(exc))
