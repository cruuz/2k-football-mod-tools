"""Qt placement canvas for APF's full-shell semantic helmet crest."""

from __future__ import annotations

from dataclasses import dataclass, replace

from PyQt5.QtCore import QPoint, QRect, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QImage, QMouseEvent, QPainter, QPainterPath, QPen
from PyQt5.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .helmet_logo_placement import (
    AUTO_TARGET_BOUNDS,
    CANVAS_HEIGHT,
    CANVAS_WIDTH,
    HelmetLogoPlacementError,
    Placement,
    PlacementResult,
    auto_fit_placement,
    render_placement,
    reset_placement,
    validate_placement,
)


@dataclass(frozen=True)
class HelmetLogoPlacementEdit:
    """Accepted flattened pixels plus their reusable original-basis transform."""

    rgba: bytes
    placement: Placement


def _display_image(rgba: bytes) -> QImage:
    """Hide black mask background so the shell guide stays visible."""

    display = bytearray(rgba)
    for offset in range(0, len(display), 4):
        if not (display[offset] or display[offset + 1] or display[offset + 2]):
            display[offset + 3] = 0
    return QImage(
        bytes(display),
        CANVAS_WIDTH,
        CANVAS_HEIGHT,
        CANVAS_WIDTH * 4,
        QImage.Format_RGBA8888,
    ).copy()


class HelmetLogoPlacementCanvas(QWidget):
    """Exact-size front/crown-to-rear canvas with direct mouse dragging."""

    placementDragged = pyqtSignal(object)

    def __init__(self, rgba: bytes, placement: Placement, parent: QWidget | None = None):
        super().__init__(parent)
        self._source_rgba = bytes(rgba)
        self._placement = placement
        self._preview = QImage()
        self._active_bbox: tuple[int, int, int, int] | None = None
        self._drag_origin: QPoint | None = None
        self._drag_placement: Placement | None = None
        self.setFixedSize(CANVAS_WIDTH, CANVAS_HEIGHT)
        self.setMouseTracking(True)
        self.setAccessibleName("Helmet logo front, crown, and rear placement canvas")
        self.setAccessibleDescription(
            "Drag the region-mask art to move it. The dotted band marks the "
            "proved full-shell front/crown-to-rear envelope."
        )
        self.setToolTip(
            "Drag to move the logo. Use Width, Height, and Rotation for exact "
            "adjustments. Red and green remain semantic team-colour regions."
        )
        self.set_placement(placement)

    @property
    def placement(self) -> Placement:
        return self._placement

    def set_placement(self, placement: Placement) -> None:
        self._placement = placement
        try:
            result = render_placement(
                self._source_rgba, placement, allow_clipping=True
            )
        except HelmetLogoPlacementError:
            self._preview = QImage()
            self._active_bbox = None
        else:
            self._preview = _display_image(result.rgba)
            self._active_bbox = result.active_bbox
        self.update()

    def paintEvent(self, _event: object) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#0b121e"))
        painter.setRenderHint(QPainter.Antialiasing, True)

        # A code-native guide avoids shipping or implying a proprietary helmet
        # render. It labels the actual U direction used by the shell carrier.
        shell = QPainterPath()
        shell.moveTo(24, 364)
        shell.cubicTo(22, 176, 126, 76, 294, 76)
        shell.cubicTo(422, 76, 490, 168, 488, 298)
        shell.lineTo(430, 370)
        shell.cubicTo(314, 402, 166, 400, 24, 364)
        painter.fillPath(shell, QColor(0, 76, 84, 105))
        painter.setPen(QPen(QColor("#70c9cf"), 2))
        painter.drawPath(shell)

        target_x_min, target_y_min, target_x_max, target_y_max = AUTO_TARGET_BOUNDS
        guide_pen = QPen(QColor("#f5c451"), 2, Qt.DashLine)
        painter.setPen(guide_pen)
        painter.drawRect(
            QRect(
                target_x_min,
                target_y_min,
                target_x_max - target_x_min,
                target_y_max - target_y_min,
            )
        )
        painter.setPen(QColor("#f5c451"))
        painter.drawText(12, 24, "FRONT / CROWN")
        painter.drawText(427, 24, "REAR")
        painter.drawText(124, 46, "FULL-SHELL TARGET  →")

        painter.setRenderHint(QPainter.SmoothPixmapTransform, False)
        if not self._preview.isNull():
            painter.drawImage(0, 0, self._preview)
        if self._active_bbox is not None:
            x_min, y_min, x_max, y_max = self._active_bbox
            painter.setPen(QPen(QColor("#ffffff"), 1, Qt.DotLine))
            painter.drawRect(QRect(x_min, y_min, x_max - x_min, y_max - y_min))
        painter.end()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.LeftButton:
            event.ignore()
            return
        self._drag_origin = event.pos()
        self._drag_placement = self._placement
        self.setCursor(Qt.ClosedHandCursor)
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_origin is None or self._drag_placement is None:
            event.ignore()
            return
        delta = event.pos() - self._drag_origin
        # Keep the dragged centre on-canvas.  The exact-value spinboxes use the
        # same 0..canvas range, so the live preview and the controls always
        # describe one identical placement -- a drag can never land somewhere
        # the numbers cannot express.
        moved = replace(
            self._drag_placement,
            center_x=min(
                CANVAS_WIDTH,
                max(0.0, self._drag_placement.center_x + delta.x()),
            ),
            center_y=min(
                CANVAS_HEIGHT,
                max(0.0, self._drag_placement.center_y + delta.y()),
            ),
        )
        self.set_placement(moved)
        self.placementDragged.emit(moved)
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton and self._drag_origin is not None:
            self._drag_origin = None
            self._drag_placement = None
            self.unsetCursor()
            event.accept()
            return
        event.ignore()


class HelmetLogoPlacementDialog(QDialog):
    """Simple Photoshop-like positioning controls around the exact canvas."""

    def __init__(
        self,
        rgba: bytes,
        *,
        auto_fit: bool,
        initial_placement: Placement | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._source_rgba = bytes(rgba)
        self._result: PlacementResult | None = None
        self.setWindowTitle("Place full-shell helmet logo")
        self.setModal(True)

        initial = initial_placement or (
            auto_fit_placement(self._source_rgba)
            if auto_fit
            else reset_placement(self._source_rgba)
        )
        root = QHBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(14)
        self.canvas = HelmetLogoPlacementCanvas(self._source_rgba, initial)
        self.canvas.placementDragged.connect(self._canvas_dragged)
        root.addWidget(self.canvas)

        side = QVBoxLayout()
        title = QLabel("Place logo across the helmet shell")
        title.setObjectName("panelTitle")
        explanation = QLabel(
            "Drag the art directly, or enter exact values. Auto-fit fills the "
            "proved front/crown-to-rear envelope. Width and Height are independent; "
            "all transforms use nearest-neighbour so region-mask colours stay exact."
        )
        explanation.setWordWrap(True)
        side.addWidget(title)
        side.addWidget(explanation)

        controls = QGridLayout()
        self.center_x = self._spin(" px", 0.0, 512.0, 1.0, 1)
        self.center_y = self._spin(" px", 0.0, 512.0, 1.0, 1)
        self.scale_x = self._spin(" %", 1.0, 6400.0, 1.0, 3)
        self.scale_y = self._spin(" %", 1.0, 6400.0, 1.0, 3)
        self.rotation = self._spin("°", -180.0, 180.0, 0.5, 1)
        rows = (
            ("X center", self.center_x),
            ("Y center", self.center_y),
            ("Width", self.scale_x),
            ("Height", self.scale_y),
            ("Rotation", self.rotation),
        )
        for row, (label, control) in enumerate(rows):
            controls.addWidget(QLabel(label), row, 0)
            controls.addWidget(control, row, 1)
            control.valueChanged.connect(self._controls_changed)
        side.addLayout(controls)

        button_row = QHBoxLayout()
        self.auto_fit_button = QPushButton("Auto-fit front → rear")
        self.reset_button = QPushButton("Reset")
        self.auto_fit_button.setToolTip(
            "Stretch the visible mask to the proved full-shell target envelope."
        )
        self.reset_button.setToolTip(
            "Restore the imported art's original size, position, and rotation."
        )
        self.auto_fit_button.clicked.connect(self._auto_fit)
        self.reset_button.clicked.connect(self._reset)
        button_row.addWidget(self.auto_fit_button)
        button_row.addWidget(self.reset_button)
        side.addLayout(button_row)

        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setObjectName("metadataText")
        side.addWidget(self.status)
        side.addStretch(1)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel
        )
        self.buttons.button(QDialogButtonBox.Save).setText("Use this placement")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        side.addWidget(self.buttons)
        root.addLayout(side, 1)

        self._set_controls(initial)
        self._refresh(initial)

    @staticmethod
    def _spin(
        suffix: str,
        minimum: float,
        maximum: float,
        step: float,
        decimals: int,
    ) -> QDoubleSpinBox:
        control = QDoubleSpinBox()
        control.setRange(minimum, maximum)
        control.setSingleStep(step)
        control.setDecimals(decimals)
        control.setSuffix(suffix)
        control.setKeyboardTracking(False)
        return control

    @property
    def placed_rgba(self) -> bytes | None:
        return self._result.rgba if self._result is not None else None

    @property
    def placement(self) -> Placement:
        return Placement(
            center_x=self.center_x.value(),
            center_y=self.center_y.value(),
            scale_x=self.scale_x.value() / 100.0,
            scale_y=self.scale_y.value() / 100.0,
            rotation_degrees=self.rotation.value(),
        )

    def _set_controls(self, placement: Placement) -> None:
        controls = (
            (self.center_x, placement.center_x),
            (self.center_y, placement.center_y),
            (self.scale_x, placement.scale_x * 100.0),
            (self.scale_y, placement.scale_y * 100.0),
            (self.rotation, placement.rotation_degrees),
        )
        for control, value in controls:
            control.blockSignals(True)
            control.setValue(value)
            control.blockSignals(False)

    def _controls_changed(self, *_args: object) -> None:
        self._refresh(self.placement)

    def _canvas_dragged(self, placement: object) -> None:
        if not isinstance(placement, Placement):
            return
        self._set_controls(placement)
        self._refresh(placement)

    def _auto_fit(self) -> None:
        placement = auto_fit_placement(self._source_rgba)
        self._set_controls(placement)
        self._refresh(placement)

    def _reset(self) -> None:
        placement = reset_placement(self._source_rgba)
        self._set_controls(placement)
        self._refresh(placement)

    def _refresh(self, placement: Placement) -> None:
        self.canvas.set_placement(placement)
        try:
            validate_placement(self._source_rgba, placement)
            result = render_placement(self._source_rgba, placement)
        except HelmetLogoPlacementError as exc:
            self._result = None
            tip = f"Move art inside the canvas before staging: {exc}"
            self.status.setText(tip)
            self.status.setStyleSheet("color: #ff8f8f;")
            # Never silent-gray: Save stays clickable; accept() re-validates and teaches.
            save = self.buttons.button(QDialogButtonBox.Save)
            save.setEnabled(True)
            save.setToolTip(tip)
            save.setProperty("disableReason", tip)
            return
        self._result = result
        x_min, y_min, x_max, y_max = result.active_bbox
        ready = (
            f"Ready • exact 512×512 • active bounds x {x_min}–{x_max}, "
            f"y {y_min}–{y_max} • {result.active_texels:,} mask texels"
        )
        self.status.setText(ready)
        self.status.setStyleSheet("color: #70d6a2;")
        save = self.buttons.button(QDialogButtonBox.Save)
        save.setEnabled(True)
        save.setToolTip("Stage this exact 512×512 helmet logo placement.")
        save.setProperty("disableReason", "")

    def accept(self) -> None:
        try:
            self._result = render_placement(self._source_rgba, self.placement)
        except HelmetLogoPlacementError as exc:
            self._result = None
            tip = str(exc)
            self.status.setText(tip)
            self.status.setStyleSheet("color: #ff8f8f;")
            save = self.buttons.button(QDialogButtonBox.Save)
            save.setEnabled(True)
            save.setToolTip(tip)
            save.setProperty("disableReason", tip)
            return
        super().accept()


def place_helmet_logo(
    rgba: bytes,
    *,
    auto_fit: bool,
    initial_placement: Placement | None = None,
    parent: QWidget | None = None,
) -> HelmetLogoPlacementEdit | None:
    """Return exact semantic RGBA and a reusable original-basis transform."""

    dialog = HelmetLogoPlacementDialog(
        rgba,
        auto_fit=auto_fit,
        initial_placement=initial_placement,
        parent=parent,
    )
    if dialog.exec_() != QDialog.Accepted:
        return None
    placed = dialog.placed_rgba
    if placed is None:
        return None
    return HelmetLogoPlacementEdit(placed, dialog.placement)


__all__ = [
    "HelmetLogoPlacementCanvas",
    "HelmetLogoPlacementDialog",
    "HelmetLogoPlacementEdit",
    "place_helmet_logo",
]
