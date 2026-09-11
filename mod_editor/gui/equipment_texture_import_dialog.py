"""Owned equipment import choice; the shared Studio panel wires this dialog."""

from __future__ import annotations

from PyQt5.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QLabel, QVBoxLayout,
)
from mod_editor.core.nfl2k5_equipment_import_intent import (
    CHOICE_CAPTION, CHOICE_HELP, PALETTE_HELP, supports_own_texture,
)


class EquipmentTextureImportDialog(QDialog):
    def __init__(self, asset, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Import equipment artwork")
        self.setMinimumWidth(460)
        layout = QVBoxLayout(self)
        target = QLabel(f"{asset.label}\nPNG size: {asset.width} x {asset.height}")
        target.setWordWrap(True)
        layout.addWidget(target)
        default = QLabel(
            "Gloves and shoes default to their own artwork, including when you copy an exported style. "
            "Untick below only for a recolour of the existing shared design. " + PALETTE_HELP)
        default.setWordWrap(True)
        layout.addWidget(default)
        self.own_texture = QCheckBox(CHOICE_CAPTION)
        self.own_texture.setObjectName("equipmentOwnTexture")
        self.own_texture.setChecked(supports_own_texture(asset.asset_id))
        self.own_texture.setEnabled(supports_own_texture(asset.asset_id))
        self.own_texture.setToolTip(CHOICE_HELP)
        layout.addWidget(self.own_texture)
        help_text = QLabel(CHOICE_HELP)
        help_text.setWordWrap(True)
        layout.addWidget(help_text)
        layout.addWidget(QLabel("Image size in the game:"))
        self.game_size = QComboBox()
        self.game_size.setObjectName("equipmentGameImageSize")
        for scale in (1, 2, 4):
            self.game_size.addItem(f"{asset.width // scale} x {asset.height // scale}"
                                  + (" (original size)" if scale == 1 else ""), scale)
        self.game_size.setEnabled(self.independent)
        self.own_texture.toggled.connect(
            lambda checked: self.game_size.setEnabled(checked and self.own_texture.isEnabled()))
        layout.addWidget(self.game_size)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Check and import")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @property
    def independent(self) -> bool:
        return self.own_texture.isEnabled() and self.own_texture.isChecked()

    @property
    def scale(self) -> int:
        return int(self.game_size.currentData()) if self.independent else 1
