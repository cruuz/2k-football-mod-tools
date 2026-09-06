"""Owned Stadiums workflow card; insertion in studio_qt is in WIRING.md."""
from pathlib import Path

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QFileDialog, QGroupBox, QLabel, QMessageBox, QPushButton, QVBoxLayout

from mod_editor.core.nfl2k5_stadium_studio import Nfl2k5StadiumStudio

WORKFLOW_TEXT = (
    "EXPERIMENTAL / UNWITNESSED\n\n"
    "1. Select a stadium and export its model. Keep the glTF and bin files together.\n"
    "2. Save the Blender helper below. Open it in Blender's Text Editor and run it. "
    "Use File > Import > NFL 2K5 Stadium.\n"
    "3. Paint the images at their original size. Select the objects you edited, then "
    "use File > Export > NFL 2K5 Stadium textures.\n"
    "4. Import that texture file here. Review the changes, save your project, and "
    "build a new game copy. Undo restores the entire texture import.\n\n"
    "Shared textures change every linked surface. Unchanged pixels stay unchanged. "
    "Detailed artwork can exceed the game's storage space. Part movement, added faces "
    "and edited UV coordinates cannot be written by this texture workflow."
)


def texture_import_summary(receipts):
    changed = sum(bool(row.changed) for row in receipts)
    unchanged = len(receipts) - changed
    return (f"{changed} texture(s) staged; {unchanged} unchanged.", changed)


class StadiumBlenderPanel(QGroupBox):
    exportRequested = pyqtSignal()
    importRequested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__("Blender textures", parent)
        layout = QVBoxLayout(self)
        label = QLabel(WORKFLOW_TEXT)
        label.setWordWrap(True)
        layout.addWidget(label)
        self.export_button = QPushButton("Export textured model")
        self.import_button = QPushButton("Import Blender textures")
        self.helper_button = QPushButton("Save Blender helper")
        for button in (self.export_button, self.helper_button, self.import_button):
            layout.addWidget(button)
        self.export_button.clicked.connect(self.exportRequested.emit)
        self.import_button.clicked.connect(self.importRequested.emit)
        self.helper_button.clicked.connect(self._save_helper)

    def _save_helper(self):
        name, _ = QFileDialog.getSaveFileName(self, "Save Blender helper", "nfl2k5_stadium.py", "Python script (*.py)")
        if not name:
            return
        try:
            source = Path(__file__).resolve().parents[2] / 'tools' / 'blender' / 'nfl2k5_stadium.py'
            target = Path(name).expanduser()
            if target.suffix.lower() != '.py':
                target = target.with_suffix('.py')
            Nfl2k5StadiumStudio._write_new_file(target, source.read_bytes())
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Could not save Blender helper", str(exc))
            return
        QMessageBox.information(self, "Blender helper saved", f"Open {target.name} in Blender's Text Editor and run it.")
