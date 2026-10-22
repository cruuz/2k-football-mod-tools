"""Install or remove Basileus Maximus' relocated play-calling patches (TU 1.1 only); all start off."""
from pathlib import Path
import tempfile

from PyQt5.QtWidgets import (QDialog, QDialogButtonBox, QFileDialog, QGroupBox, QHBoxLayout, QLabel,
                             QMessageBox, QPushButton, QVBoxLayout)

from mod_editor.core import apf2k8_community_patches as model
from mod_editor.core.errors import ValidationError
from .launcher import COMMUNITY_PATCH_KINDS, LaunchError

KIND_BY_KEY = {key: kind for kind, key in COMMUNITY_PATCH_KINDS.items()}
CREDIT = (f"Community patches by {model.AUTHOR}, shared with his permission. Xenia, Title Update 1.1 only. "
          "The Studio relocated their code caves into its own reserved space so they work together with the Studio's "
          "charge-abilities, fourth-down, pass-fetch and situation patches; the code is otherwise his. Off until you "
          "install them. In-game results with Studio builds are UNWITNESSED.")


class CommunityPatchesDialog(QDialog):
    def __init__(self, launcher, parent=None):
        super().__init__(parent)
        self.launcher = launcher
        self.setWindowTitle(f"Community play-calling patches ({model.AUTHOR})")
        self.resize(760, 620)
        root = QVBoxLayout(self)
        note = QLabel(CREDIT)
        note.setWordWrap(True)
        root.addWidget(note)
        self.warning = QLabel()
        self.warning.setWordWrap(True)
        root.addWidget(self.warning)
        self.status = {}
        self.install_buttons = {}
        for row in model.load_definitions():
            box = QGroupBox(row.name.split(":")[0])
            layout = QVBoxLayout(box)
            text = QLabel(row.name)
            text.setWordWrap(True)
            text.setToolTip(row.desc)
            layout.addWidget(text)
            buttons = QHBoxLayout()
            install = QPushButton("Review and install…")
            install.clicked.connect(lambda _=False, key=row.key: self.install(key))
            remove = QPushButton("Remove")
            remove.clicked.connect(lambda _=False, key=row.key: self.remove(key))
            export = QPushButton("Export…")
            export.clicked.connect(lambda _=False, key=row.key: self.export(key))
            for button in (install, remove, export):
                buttons.addWidget(button)
            layout.addLayout(buttons)
            status = QLabel()
            status.setWordWrap(True)
            layout.addWidget(status)
            self.status[row.key] = status
            self.install_buttons[row.key] = install
            root.addWidget(box)
        close = QDialogButtonBox(QDialogButtonBox.Close)
        close.rejected.connect(self.reject)
        root.addWidget(close)
        self.refresh()

    def refresh(self):
        for key, label in self.status.items():
            label.setText(self.launcher.pass_fetch_status(kind=KIND_BY_KEY[key])["message"])
        upstream = []
        if self.launcher.settings.xenia_path is not None:
            upstream = model.upstream_conflicts(self.launcher.settings.patches_folder)
        self.warning.setText(
            "Original (unrelocated) copies found in the Xenia patches folder: " + ", ".join(upstream)
            + ". Their caves overwrite the charge-abilities patch; remove them and use these copies instead."
            if upstream else "")

    def install(self, key):
        if not self.launcher.settings.configured:
            self.status[key].setText("Configure Xenia Edge or Canary in the Studio first, then install the patch.")
            return
        row = model.definition(key)
        answer = QMessageBox.question(
            self, "Install community patch?",
            f"Install \"{row.name}\" by {model.AUTHOR} and enable Xenia patches? It applies to Title Update 1.1 "
            "only. This also activates other installed patches marked enabled. Restart Xenia after changing "
            "patches. The in-game result with Studio builds is UNWITNESSED.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer != QMessageBox.Yes:
            return
        try:
            with tempfile.TemporaryDirectory(prefix="apf-community-patch-") as temporary:
                source = Path(temporary) / row.filename
                model.write_patch(model.PatchDocument(row, True), source)
                self.launcher.install_pass_fetch_patch(source, kind=KIND_BY_KEY[key], consent=True)
        except (OSError, ValueError, ValidationError, LaunchError) as exc:
            self.status[key].setText(str(exc))
            return
        self.refresh()

    def remove(self, key):
        try:
            self.launcher.remove_pass_fetch_patch(kind=KIND_BY_KEY[key])
        except (OSError, ValueError, ValidationError, LaunchError) as exc:
            self.status[key].setText(str(exc))
            return
        self.refresh()

    def export(self, key):
        row = model.definition(key)
        path, _ = QFileDialog.getSaveFileName(self, "Export community patch", row.filename, "Xenia patch (*.patch.toml)")
        if not path:
            return
        try:
            model.write_patch(model.PatchDocument(row, True), Path(path))
            self.status[key].setText(f"Exported to {path}. Title Update 1.1 only.")
        except (OSError, ValueError, ValidationError) as exc:
            self.status[key].setText(str(exc))
