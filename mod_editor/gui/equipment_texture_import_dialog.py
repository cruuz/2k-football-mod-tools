"""Owned equipment import choice; the shared Studio panel wires this dialog."""

from __future__ import annotations

from PyQt5.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QLabel, QVBoxLayout,
)
from mod_editor.core.nfl2k5_equipment_import_intent import (
    CHOICE_CAPTION, CHOICE_HELP, PALETTE_HELP, SHOE_ROUTE_HELP, LARGER_ART_HELP, supports_own_texture,
)


from mod_editor.core.nfl2k5_equipment_import import (
    equipment_import_scope,
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
        choices, rule = equipment_import_scope(asset.asset_id)
        layout.addWidget(QLabel("Import applies to:"))
        self.import_scope = QComboBox()
        self.import_scope.setObjectName("equipmentImportScope")
        for value, caption in choices:
            self.import_scope.addItem(caption, value)
        layout.addWidget(self.import_scope)
        scope_note = QLabel(rule)
        scope_note.setObjectName("equipmentScopeExplanation")
        scope_note.setWordWrap(True)
        layout.addWidget(scope_note)
        if ":shoes" in asset.asset_id:
            local_note = QLabel(SHOE_ROUTE_HELP)
            local_note.setWordWrap(True)
            layout.addWidget(local_note)
        default = QLabel(
            "Socks, gloves and shoes default to their own artwork, including when you copy an exported style. "
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

    @property
    def scope(self) -> str:
        return str(self.import_scope.currentData())


class EquipmentFitRetryDialog(QDialog):
    """Offer only the writer's checked retry; the Studio re-runs the import."""

    def __init__(self, asset, failure, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Equipment artwork needs less space")
        self.setMinimumWidth(460)
        layout = QVBoxLayout(self)
        detail = QLabel(str(failure))
        detail.setWordWrap(True)
        detail.setObjectName("equipmentFitArithmetic")
        layout.addWidget(detail)
        growth = QLabel(LARGER_ART_HELP)
        growth.setWordWrap(True)
        layout.addWidget(growth)
        suggestion = getattr(failure, "suggestion", None)
        self.scale = None
        if (isinstance(suggestion, dict) and suggestion.get("asset_id") == asset.asset_id
                and suggestion.get("scale") in (2, 4)):
            self.scale = suggestion["scale"]
        buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        self.try_that = buttons.addButton("Try that", QDialogButtonBox.AcceptRole)
        self.try_that.setObjectName("equipmentTryThat")
        self.try_that.setEnabled(self.scale is not None)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
