"""Qt confirmation and preview for normal APF helmet-logo artwork."""

from __future__ import annotations

import math

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .helmet_logo_regions import (
    CANVAS_HEIGHT,
    CANVAS_WIDTH,
    HelmetLogoRegionError,
    NormalLogoConversion,
    TwoRegionPalette,
    convert_normal_logo_to_region_mask,
    suggest_two_region_palette,
)


def _pixmap(rgba: bytes) -> QPixmap:
    image = QImage(
        rgba,
        CANVAS_WIDTH,
        CANVAS_HEIGHT,
        CANVAS_WIDTH * 4,
        QImage.Format_RGBA8888,
    ).copy()
    return QPixmap.fromImage(image).scaled(
        260, 260, Qt.KeepAspectRatio, Qt.SmoothTransformation
    )


def _hex(rgb: tuple[int, int, int]) -> str:
    return "#" + "".join(f"{channel:02X}" for channel in rgb)


def _parse_hex(text: str, label: str) -> tuple[int, int, int]:
    value = text.strip().removeprefix("#")
    if len(value) != 6 or any(character not in "0123456789abcdefABCDEF" for character in value):
        raise HelmetLogoRegionError(f"{label} must be exactly six RGB hex digits.")
    return tuple(int(value[index : index + 2], 16) for index in (0, 2, 4))  # type: ignore[return-value]


class NormalLogoRegionDialog(QDialog):
    """Require an explicit palette mapping before ordinary art becomes a mask."""

    def __init__(self, rgba: bytes, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._source_rgba = bytes(rgba)
        self._conversion: NormalLogoConversion | None = None
        self.setWindowTitle("Convert normal logo to APF color regions")
        self.setModal(True)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)
        title = QLabel("Confirm how the game should recolor this logo")
        title.setObjectName("panelTitle")
        explanation = QLabel(
            "APF does not store literal logo RGB on the helmet. It stores palette "
            "weights. Confirm the rendered helmet shell and two detail colors below; "
            "Mod Studio converts the artwork to exact four-bit red/green region "
            "weights, then the placement canvas handles size and position."
        )
        explanation.setWordWrap(True)
        root.addWidget(title)
        root.addWidget(explanation)

        suggestion = suggest_two_region_palette(self._source_rgba)
        self.suggestion_note = QLabel(suggestion.explanation)
        self.suggestion_note.setObjectName("findingText")
        self.suggestion_note.setWordWrap(True)
        root.addWidget(self.suggestion_note)

        palette_grid = QGridLayout()
        palette_grid.addWidget(QLabel("Role"), 0, 0)
        palette_grid.addWidget(QLabel("Rendered RGB"), 0, 1)
        palette_grid.addWidget(QLabel("Stored meaning"), 0, 2)
        self.shell = self._field("Helmet shell rendered RGB", "e.g. #003562")
        self.red_region = self._field("Red-region rendered RGB", "e.g. #FFC72C")
        self.green_region = self._field("Green-region rendered RGB", "e.g. #FFFFFF")
        rows = (
            ("Helmet shell / background", self.shell, "zero RGB weight"),
            ("Detail color 1", self.red_region, "red mask channel"),
            ("Detail color 2", self.green_region, "green mask channel"),
        )
        for row, (label, field, meaning) in enumerate(rows, start=1):
            palette_grid.addWidget(QLabel(label), row, 0)
            palette_grid.addWidget(field, row, 1)
            palette_grid.addWidget(QLabel(meaning), row, 2)
        root.addLayout(palette_grid)
        if suggestion.palette is not None:
            self.set_palette(suggestion.palette)

        previews = QHBoxLayout()
        source_column = QVBoxLayout()
        source_column.addWidget(QLabel("Imported artwork"))
        self.source_preview = QLabel()
        self.source_preview.setFixedSize(264, 264)
        self.source_preview.setAlignment(Qt.AlignCenter)
        self.source_preview.setPixmap(_pixmap(self._source_rgba))
        self.source_preview.setAccessibleName("Imported normal helmet logo preview")
        source_column.addWidget(self.source_preview)
        previews.addLayout(source_column)

        result_column = QVBoxLayout()
        result_column.addWidget(QLabel("Palette-mapped material preview"))
        self.material_preview = QLabel("Enter all three RGB values, then update preview.")
        self.material_preview.setFixedSize(264, 264)
        self.material_preview.setAlignment(Qt.AlignCenter)
        self.material_preview.setWordWrap(True)
        self.material_preview.setAccessibleName("APF palette-mapped helmet logo preview")
        result_column.addWidget(self.material_preview)
        previews.addLayout(result_column)
        root.addLayout(previews)

        update_row = QHBoxLayout()
        self.update_button = QPushButton("Update material preview")
        self.update_button.setObjectName("secondaryButton")
        self.update_button.clicked.connect(self.refresh_preview)
        self.status = QLabel(
            "This preview is palette math, not a promise of literal source RGB or gameplay visibility."
        )
        self.status.setWordWrap(True)
        self.status.setObjectName("metadataText")
        update_row.addWidget(self.update_button)
        update_row.addWidget(self.status, 1)
        root.addLayout(update_row)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Save).setText("Use palette-mapped mask")
        # Never silent-gray: stay clickable; accept path explains when invalid.
        self.buttons.button(QDialogButtonBox.Save).setEnabled(True)
        self.buttons.button(QDialogButtonBox.Save).setToolTip(
            "Update the material preview first so the palette-mapped mask is valid."
        )
        self.buttons.button(QDialogButtonBox.Save).setProperty(
            "disableReason",
            "Update the material preview first so the palette-mapped mask is valid.",
        )
        self.buttons.accepted.connect(self._accept_if_valid)
        self.buttons.rejected.connect(self.reject)
        root.addWidget(self.buttons)
        for field in (self.shell, self.red_region, self.green_region):
            field.textChanged.connect(self._mapping_changed)
        if suggestion.palette is not None:
            self.refresh_preview()

    @staticmethod
    def _field(accessible_name: str, placeholder: str) -> QLineEdit:
        field = QLineEdit()
        field.setMaxLength(7)
        field.setPlaceholderText(placeholder)
        field.setAccessibleName(accessible_name)
        field.setToolTip(
            "Rendered preview color as #RRGGBB. This is a confirmed mapping input; "
            "it is not copied literally into the game's crest texture."
        )
        return field

    @property
    def conversion(self) -> NormalLogoConversion | None:
        return self._conversion

    def palette(self) -> TwoRegionPalette:
        return TwoRegionPalette(
            shell=_parse_hex(self.shell.text(), "Helmet shell RGB"),
            red_region=_parse_hex(self.red_region.text(), "Detail color 1 RGB"),
            green_region=_parse_hex(self.green_region.text(), "Detail color 2 RGB"),
        )

    def set_palette(self, palette: TwoRegionPalette) -> None:
        self.shell.setText(_hex(palette.shell))
        self.red_region.setText(_hex(palette.red_region))
        self.green_region.setText(_hex(palette.green_region))

    def refresh_preview(self) -> bool:
        try:
            conversion = convert_normal_logo_to_region_mask(
                self._source_rgba, self.palette()
            )
        except HelmetLogoRegionError as exc:
            self._conversion = None
            self.material_preview.clear()
            self.material_preview.setText(str(exc))
            self.status.setText(str(exc))
            save = self.buttons.button(QDialogButtonBox.Save)
            save.setEnabled(True)
            save.setToolTip(str(exc))
            save.setProperty("disableReason", str(exc))
            return False
        self._conversion = conversion
        self.material_preview.setPixmap(_pixmap(conversion.material_preview_rgba))
        rmse = math.sqrt(conversion.mean_squared_rgb_error)
        self.status.setText(
            f"Ready: {conversion.validation.active_texels:,} weighted texels; "
            f"palette-preview RGB error max {conversion.maximum_rgb_error}, "
            f"RMSE {rmse:.2f}. Confirm these colors before continuing."
        )
        save = self.buttons.button(QDialogButtonBox.Save)
        save.setEnabled(True)
        save.setToolTip("Use this palette-mapped region mask.")
        save.setProperty("disableReason", "")
        return True

    def _mapping_changed(self, _text: str) -> None:
        self._conversion = None
        self.material_preview.clear()
        self.material_preview.setText(
            "Mapping changed. Update the material preview before continuing."
        )
        self.status.setText(
            "Confirm the edited rendered colors by updating the palette-mapped preview."
        )
        save = self.buttons.button(QDialogButtonBox.Save)
        save.setEnabled(True)
        tip = "Update the material preview first so the palette-mapped mask is valid."
        save.setToolTip(tip)
        save.setProperty("disableReason", tip)

    def _accept_if_valid(self) -> None:
        reason = str(
            self.buttons.button(QDialogButtonBox.Save).property("disableReason") or ""
        ).strip()
        if reason:
            from PyQt5.QtWidgets import QMessageBox

            QMessageBox.information(
                self,
                "Preview first",
                reason + "\n\nClick “Update material preview”, then Use mask.",
            )
            return
        if self._conversion is not None:
            self.accept()


def convert_normal_logo(
    rgba: bytes, *, parent: QWidget | None = None
) -> NormalLogoConversion | None:
    """Run explicit color confirmation; return only a semantic APF mask."""

    dialog = NormalLogoRegionDialog(rgba, parent)
    if dialog.exec_() != QDialog.Accepted:
        return None
    return dialog.conversion


__all__ = [
    "NormalLogoRegionDialog",
    "convert_normal_logo",
]
