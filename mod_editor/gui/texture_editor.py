"""A built-in pixel editor for one texture slot, shared by both Mod Studios.

Editing a game texture used to mean exporting a PNG, opening another program,
remembering not to change its size or flatten its alpha, and importing it back.
Every one of those steps has bitten someone: a resaved 512x256 that came back
513x256, a jersey flattened onto white, a crest that lost its transparency.

This edits the slot in place at its exact retail size, so the size can never
drift -- the canvas simply is that many pixels and there is no resize control.
What comes out is always exactly what the writer expects.

Deliberate choices worth stating:

* **Nearest-neighbour zoom.** These textures are small and blocky; smoothing
  them at 8x would hide exactly the pixel you are trying to place.
* **A chequerboard under everything.** Alpha matters enormously here -- a crest
  with the wrong transparency is a black box on a helmet -- so transparency is
  always visible rather than being drawn as white.
* **Whole-image undo snapshots.** Coarse, but a 512x512 texture is 1 MiB, so
  twenty-four steps costs about 24 MiB and cannot get out of step with the
  canvas the way a replayed-operation stack can. Stability beats cleverness.
* **Nothing is written until Save.** Cancel leaves the slot exactly as it was.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from PyQt5.QtCore import QPoint, QRect, QSize, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QImage, QMouseEvent, QPainter, QPixmap, QWheelEvent
from PyQt5.QtWidgets import (
    QColorDialog, QDialog, QDialogButtonBox, QFrame, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QSizePolicy, QSpinBox, QVBoxLayout, QWidget,
)


ZOOM_STEPS = (1, 2, 3, 4, 6, 8, 12, 16)
MAX_UNDO = 24
TOOLS = ("pencil", "eraser", "picker", "fill")


@dataclass(frozen=True)
class EditorResult:
    """The finished pixels, at exactly the size the slot demands."""

    width: int
    height: int
    rgba: bytes


def _chequer(size: int = 8) -> QPixmap:
    """The under-layer that makes transparency visible rather than white."""
    pixmap = QPixmap(size * 2, size * 2)
    pixmap.fill(QColor(56, 62, 74))
    painter = QPainter(pixmap)
    painter.fillRect(0, 0, size, size, QColor(74, 82, 96))
    painter.fillRect(size, size, size, size, QColor(74, 82, 96))
    painter.end()
    return pixmap


class TextureCanvas(QWidget):
    """The zoomable pixel surface. Owns the image; the dialog owns the tools."""

    color_picked = pyqtSignal(QColor)
    image_changed = pyqtSignal()
    cursor_moved = pyqtSignal(int, int)

    def __init__(self, image: QImage, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._image = image.convertToFormat(QImage.Format_RGBA8888)
        self._zoom = 1
        self._tool = "pencil"
        self._color = QColor(255, 255, 255, 255)
        self._brush = 1
        self._undo: list[QImage] = []
        self._redo: list[QImage] = []
        self._stroke_open = False
        self._chequer = _chequer()
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self._resize_to_zoom()

    # -- state -------------------------------------------------------------
    @property
    def image(self) -> QImage:
        return self._image

    @property
    def zoom(self) -> int:
        return self._zoom

    def set_zoom(self, zoom: int) -> None:
        self._zoom = max(ZOOM_STEPS[0], min(ZOOM_STEPS[-1], int(zoom)))
        self._resize_to_zoom()
        self.update()

    def set_tool(self, tool: str) -> None:
        if tool in TOOLS:
            self._tool = tool

    def set_color(self, color: QColor) -> None:
        self._color = QColor(color)

    def set_brush(self, size: int) -> None:
        self._brush = max(1, min(64, int(size)))

    def _resize_to_zoom(self) -> None:
        self.setFixedSize(
            QSize(self._image.width() * self._zoom,
                  self._image.height() * self._zoom)
        )

    # -- history -----------------------------------------------------------
    def _snapshot(self) -> None:
        self._undo.append(self._image.copy())
        if len(self._undo) > MAX_UNDO:
            self._undo.pop(0)
        self._redo.clear()

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    def undo(self) -> None:
        if not self._undo:
            return
        self._redo.append(self._image.copy())
        self._image = self._undo.pop()
        self.update()
        self.image_changed.emit()

    def redo(self) -> None:
        if not self._redo:
            return
        self._undo.append(self._image.copy())
        self._image = self._redo.pop()
        self.update()
        self.image_changed.emit()

    # -- painting ----------------------------------------------------------
    def paintEvent(self, _event: object) -> None:
        painter = QPainter(self)
        painter.drawTiledPixmap(self.rect(), self._chequer)
        # Nearest-neighbour: at 8x a smoothed pixel is a lie about where it is.
        painter.setRenderHint(QPainter.SmoothPixmapTransform, False)
        painter.drawImage(
            QRect(0, 0, self._image.width() * self._zoom,
                  self._image.height() * self._zoom),
            self._image,
        )
        if self._zoom >= 8:
            painter.setPen(QColor(255, 255, 255, 28))
            for x in range(0, self._image.width() + 1):
                painter.drawLine(x * self._zoom, 0,
                                 x * self._zoom, self.height())
            for y in range(0, self._image.height() + 1):
                painter.drawLine(0, y * self._zoom,
                                 self.width(), y * self._zoom)
        painter.end()

    # -- input -------------------------------------------------------------
    def _pixel_at(self, position: QPoint) -> tuple[int, int] | None:
        x = position.x() // self._zoom
        y = position.y() // self._zoom
        if 0 <= x < self._image.width() and 0 <= y < self._image.height():
            return int(x), int(y)
        return None

    def mousePressEvent(self, event: QMouseEvent) -> None:
        spot = self._pixel_at(event.pos())
        if spot is None:
            return
        if self._tool == "picker":
            self.color_picked.emit(QColor(self._image.pixelColor(*spot)))
            return
        self._snapshot()
        self._stroke_open = True
        if self._tool == "fill":
            self._flood(*spot)
        else:
            self._dab(*spot)
        self.update()
        self.image_changed.emit()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        spot = self._pixel_at(event.pos())
        if spot is not None:
            self.cursor_moved.emit(*spot)
        if not self._stroke_open or spot is None or self._tool == "fill":
            return
        self._dab(*spot)
        self.update()

    def mouseReleaseEvent(self, _event: QMouseEvent) -> None:
        if self._stroke_open:
            self._stroke_open = False
            self.image_changed.emit()

    def wheelEvent(self, event: QWheelEvent) -> None:
        if event.modifiers() & Qt.ControlModifier:
            step = 1 if event.angleDelta().y() > 0 else -1
            current = min(range(len(ZOOM_STEPS)),
                          key=lambda i: abs(ZOOM_STEPS[i] - self._zoom))
            self.set_zoom(ZOOM_STEPS[max(0, min(len(ZOOM_STEPS) - 1,
                                                current + step))])
            event.accept()
            return
        event.ignore()

    # -- drawing -----------------------------------------------------------
    def _dab(self, x: int, y: int) -> None:
        colour = (QColor(0, 0, 0, 0) if self._tool == "eraser"
                  else QColor(self._color))
        half = self._brush // 2
        for dy in range(-half, self._brush - half):
            for dx in range(-half, self._brush - half):
                px, py = x + dx, y + dy
                if 0 <= px < self._image.width() and 0 <= py < self._image.height():
                    self._image.setPixelColor(px, py, colour)

    def _flood(self, x: int, y: int) -> None:
        """Scanline flood fill. Bounded by the image, so it always terminates."""
        target = self._image.pixelColor(x, y).rgba()
        replacement = (QColor(0, 0, 0, 0) if self._tool == "eraser"
                       else QColor(self._color))
        if target == replacement.rgba():
            return
        width, height = self._image.width(), self._image.height()
        stack = [(x, y)]
        seen = bytearray(width * height)
        while stack:
            sx, sy = stack.pop()
            if not (0 <= sx < width and 0 <= sy < height):
                continue
            if seen[sy * width + sx]:
                continue
            if self._image.pixelColor(sx, sy).rgba() != target:
                continue
            seen[sy * width + sx] = 1
            self._image.setPixelColor(sx, sy, replacement)
            stack.extend(((sx + 1, sy), (sx - 1, sy), (sx, sy + 1), (sx, sy - 1)))


class TextureEditorDialog(QDialog):
    """Edit one slot's pixels and hand back exactly its retail size."""

    def __init__(
        self,
        rgba: bytes,
        width: int,
        height: int,
        label: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        if len(rgba) != width * height * 4:
            raise ValueError(
                f"{label}: expected {width * height * 4} RGBA bytes, got {len(rgba)}"
            )
        self.setWindowTitle(f"Edit {label} — {width}×{height}")
        self.setModal(True)
        self._width, self._height = width, height

        image = QImage(bytes(rgba), width, height, width * 4,
                       QImage.Format_RGBA8888).copy()
        self.canvas = TextureCanvas(image, self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        bar = QHBoxLayout()
        bar.setSpacing(8)
        self._tool_buttons: dict[str, QPushButton] = {}
        for tool, text in (("pencil", "Pencil"), ("eraser", "Eraser"),
                           ("picker", "Pick colour"), ("fill", "Fill")):
            button = QPushButton(text)
            button.setCheckable(True)
            button.setObjectName("secondaryButton")
            button.clicked.connect(
                lambda _checked=False, name=tool: self._select_tool(name)
            )
            bar.addWidget(button)
            self._tool_buttons[tool] = button

        self.colour_button = QPushButton("Colour…")
        self.colour_button.clicked.connect(self._choose_colour)
        bar.addWidget(self.colour_button)

        bar.addWidget(QLabel("Brush"))
        self.brush_spin = QSpinBox()
        self.brush_spin.setRange(1, 64)
        self.brush_spin.valueChanged.connect(self.canvas.set_brush)
        bar.addWidget(self.brush_spin)

        bar.addStretch(1)
        self.zoom_out = QPushButton("−")
        self.zoom_in = QPushButton("+")
        self.zoom_label = QLabel("100%")
        for widget in (self.zoom_out, self.zoom_label, self.zoom_in):
            bar.addWidget(widget)
        self.zoom_out.clicked.connect(lambda: self._step_zoom(-1))
        self.zoom_in.clicked.connect(lambda: self._step_zoom(1))

        self.undo_button = QPushButton("Undo")
        self.redo_button = QPushButton("Redo")
        self.undo_button.clicked.connect(self.canvas.undo)
        self.redo_button.clicked.connect(self.canvas.redo)
        bar.addWidget(self.undo_button)
        bar.addWidget(self.redo_button)
        layout.addLayout(bar)

        scroll = QScrollArea()
        scroll.setWidgetResizable(False)
        scroll.setAlignment(Qt.AlignCenter)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(self.canvas)
        layout.addWidget(scroll, 1)

        self.status = QLabel(
            f"{width}×{height} — the size is fixed by the game, so what you "
            "save is always the right shape. Ctrl+scroll to zoom."
        )
        self.status.setObjectName("mutedLabel")
        layout.addWidget(self.status)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.canvas.color_picked.connect(self._adopt_colour)
        self.canvas.image_changed.connect(self._refresh_history)
        self.canvas.cursor_moved.connect(self._report_cursor)
        self._colour = QColor(255, 255, 255, 255)
        self._select_tool("pencil")
        self._paint_colour_button()
        self._refresh_history()
        self._update_zoom_label()

    # -- toolbar -----------------------------------------------------------
    def _select_tool(self, tool: str) -> None:
        self.canvas.set_tool(tool)
        for name, button in self._tool_buttons.items():
            button.setChecked(name == tool)

    def _choose_colour(self) -> None:
        chosen = QColorDialog.getColor(
            self._colour, self, "Choose a colour",
            QColorDialog.ShowAlphaChannel,
        )
        if chosen.isValid():
            self._adopt_colour(chosen)

    def _adopt_colour(self, colour: QColor) -> None:
        """Used by both the dialog and the eyedropper, so picking a colour off
        the texture immediately becomes the colour you paint with."""
        self._colour = QColor(colour)
        self.canvas.set_color(self._colour)
        self._paint_colour_button()

    def _paint_colour_button(self) -> None:
        readable = "#101828" if self._colour.lightness() > 140 else "#edf3fc"
        self.colour_button.setStyleSheet(
            f"background:{self._colour.name()};color:{readable};"
            "border:1px solid #2b3d5f;border-radius:8px;padding:6px 12px;"
        )
        self.colour_button.setText(
            f"{self._colour.name().upper()}  α{self._colour.alpha()}"
        )

    def _step_zoom(self, direction: int) -> None:
        current = min(range(len(ZOOM_STEPS)),
                      key=lambda i: abs(ZOOM_STEPS[i] - self.canvas.zoom))
        index = max(0, min(len(ZOOM_STEPS) - 1, current + direction))
        self.canvas.set_zoom(ZOOM_STEPS[index])
        self._update_zoom_label()

    def _update_zoom_label(self) -> None:
        self.zoom_label.setText(f"{self.canvas.zoom * 100}%")

    def _refresh_history(self) -> None:
        self.undo_button.setEnabled(self.canvas.can_undo)
        self.redo_button.setEnabled(self.canvas.can_redo)

    def _report_cursor(self, x: int, y: int) -> None:
        colour = self.canvas.image.pixelColor(x, y)
        self.status.setText(
            f"{self._width}×{self._height} — cursor {x}, {y} · "
            f"{colour.name().upper()} α{colour.alpha()} · Ctrl+scroll to zoom"
        )

    # -- result ------------------------------------------------------------
    def result_rgba(self) -> EditorResult:
        image = self.canvas.image.convertToFormat(QImage.Format_RGBA8888)
        pointer = image.constBits()
        pointer.setsize(image.byteCount())
        rgba = bytes(pointer)
        expected = self._width * self._height * 4
        if len(rgba) != expected:  # pragma: no cover - Qt row padding guard
            rows = []
            stride = image.bytesPerLine()
            for y in range(self._height):
                rows.append(rgba[y * stride:y * stride + self._width * 4])
            rgba = b"".join(rows)
        return EditorResult(self._width, self._height, rgba)


def edit_texture(
    rgba: bytes,
    width: int,
    height: int,
    label: str,
    parent: QWidget | None = None,
    on_save: Callable[[EditorResult], None] | None = None,
) -> EditorResult | None:
    """Open the editor. Returns the edited pixels, or None if cancelled."""
    dialog = TextureEditorDialog(rgba, width, height, label, parent)
    if dialog.exec_() != QDialog.Accepted:
        return None
    result = dialog.result_rgba()
    if on_save is not None:
        on_save(result)
    return result


__all__ = [
    "MAX_UNDO",
    "TOOLS",
    "ZOOM_STEPS",
    "EditorResult",
    "TextureCanvas",
    "TextureEditorDialog",
    "edit_texture",
]
