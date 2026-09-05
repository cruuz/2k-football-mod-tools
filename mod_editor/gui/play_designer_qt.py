"""Formation Designer and Play Designer dialogs for NFL 2K5 playbooks.

Both dialogs work on the private PLAY body bytes and the retail codec in
``mod_editor.core.nfl2k5_play_codec``.  They produce the ``slot_positions`` /
``assignments`` payloads that the formation/play create writer compiles; the
play designer runs the ported retail validator live so a play the game would
refuse is flagged before it is staged.
"""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass
from typing import Callable

from PyQt5.QtCore import QPointF, QRectF, Qt
from PyQt5.QtGui import QBrush, QColor, QFont, QPainter, QPen, QPolygonF
from PyQt5.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout,
    QGraphicsEllipseItem, QGraphicsItem, QGraphicsScene, QGraphicsSimpleTextItem,
    QGraphicsView, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMessageBox, QPushButton, QSpinBox, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from mod_editor.core import nfl2k5_play_codec as codec
from mod_editor.core import nfl2k5_play_library as lib
from mod_editor.core.nfl2k5_playbook_inspector import (
    CATEGORY_BASE, CATEGORY_SIZE, FORMATION_AUX_BASE, FORMATION_AUX_SIZE, FORMATION_BASE,
    FORMATION_SIZE, NODE_BASE, NODE_SIZE, PLAY_BASE, PLAY_SIZE, Nfl2k5Playbook,
)

YD = codec.YD_CM
PX_PER_YD = 16.0
FIELD_HALF_WIDTH_YD = 26.67
FIELD_DEPTH_YD = 20.0      # backfield shown
FIELD_DOWN_YD = 30.0       # downfield shown


# ---------------------------------------------------------------------------
# Book helpers
# ---------------------------------------------------------------------------

def formation_record(body: bytes, index: int) -> codec.FormationRecord:
    off = FORMATION_BASE + index * FORMATION_SIZE
    return codec.FormationRecord.from_bytes(body[off:off + FORMATION_SIZE])


def formation_category_index(body: bytes, index: int) -> int:
    aux = FORMATION_AUX_BASE + index * FORMATION_AUX_SIZE
    return struct.unpack_from("<I", body, aux + 0x48)[0] & 0x3F


def category_positions(body: bytes, category_index: int) -> list[int]:
    off = CATEGORY_BASE + category_index * CATEGORY_SIZE
    return list(body[off + 5:off + 16])


def play_chains(body: bytes, play_index: int) -> tuple[int, list[tuple[int, list[bytes]]]]:
    off = PLAY_BASE + play_index * PLAY_SIZE
    flags = struct.unpack_from("<I", body, off + 4)[0]
    out: list[tuple[int, list[bytes]]] = []
    for slot in range(11):
        desc = struct.unpack_from("<I", body, off + 8 + slot * 8)[0]
        ptr_field = off + 0x0C + slot * 8
        target = ptr_field - 1 + struct.unpack_from("<i", body, ptr_field)[0]
        nodes = [body[target + k * NODE_SIZE: target + (k + 1) * NODE_SIZE] for k in range(desc & 0xF)]
        out.append((desc, nodes))
    return flags, out


def is_offense_formation(record: codec.FormationRecord) -> bool:
    return record.type_code < 4 or record.type_code in (10, 12, 8)


# ---------------------------------------------------------------------------
# Field canvas
# ---------------------------------------------------------------------------

def to_scene(x_cm: float, z_cm: float) -> QPointF:
    return QPointF(x_cm / YD * PX_PER_YD, -z_cm / YD * PX_PER_YD)


def from_scene(pt: QPointF) -> tuple[float, float]:
    return pt.x() / PX_PER_YD * YD, -pt.y() / PX_PER_YD * YD


class PlayerToken(QGraphicsEllipseItem):
    RADIUS = 9.0

    def __init__(self, slot: int, label: str, movable: bool, on_moved: Callable[[int], None], on_selected: Callable[[int], None]):
        super().__init__(-self.RADIUS, -self.RADIUS, 2 * self.RADIUS, 2 * self.RADIUS)
        self.slot = slot
        self.on_moved = on_moved
        self.on_selected = on_selected
        self.setBrush(QBrush(QColor("#f3e7c8")))
        self.setPen(QPen(QColor("#1d1d1d"), 1.5))
        self.setFlag(QGraphicsItem.ItemIsMovable, movable)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setZValue(10)
        self.text = QGraphicsSimpleTextItem(label, self)
        font = QFont()
        font.setPointSizeF(6.5)
        font.setBold(True)
        self.text.setFont(font)
        rect = self.text.boundingRect()
        self.text.setPos(-rect.width() / 2, -rect.height() / 2)
        self.setToolTip(f"slot {slot}: {label}")

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if self.flags() & QGraphicsItem.ItemIsMovable:
            x_cm, z_cm = from_scene(self.pos())
            step = YD / 4.0
            x_cm = round(x_cm / step) * step
            z_cm = round(z_cm / step) * step
            self.setPos(to_scene(x_cm, z_cm))
            self.on_moved(self.slot)

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        self.on_selected(self.slot)


class FieldScene(QGraphicsScene):
    def __init__(self, offense: bool = True):
        super().__init__()
        self.offense = offense
        self.tokens: dict[int, PlayerToken] = {}
        self.art_items: list = []
        self.setBackgroundBrush(QBrush(QColor("#2e7d32")))
        self._draw_field()

    def _draw_field(self) -> None:
        w = FIELD_HALF_WIDTH_YD * PX_PER_YD
        top = -FIELD_DOWN_YD * PX_PER_YD
        bottom = FIELD_DEPTH_YD * PX_PER_YD
        self.setSceneRect(QRectF(-w - 20, top - 20, 2 * w + 40, bottom - top + 40))
        stripe = QPen(QColor("#ffffff"), 1)
        stripe.setCosmetic(True)
        faint = QPen(QColor("#a5d6a7"), 1, Qt.DotLine)
        faint.setCosmetic(True)
        for yd in range(-int(FIELD_DEPTH_YD), int(FIELD_DOWN_YD) + 1, 5):
            y = -yd * PX_PER_YD
            self.addLine(-w, y, w, y, stripe if yd == 0 else faint)
            label = self.addSimpleText("LOS" if yd == 0 else f"{yd:+d}")
            label.setBrush(QBrush(QColor("#e8f5e9")))
            label.setPos(w + 4, y - 7)
        for x_yd in (-FIELD_HALF_WIDTH_YD, -3.1, 3.1, FIELD_HALF_WIDTH_YD):
            x = x_yd * PX_PER_YD
            pen = stripe if abs(x_yd) > 20 else faint
            self.addLine(x, top, x, bottom, pen)
        los = self.addLine(-w, 0, w, 0, QPen(QColor("#ffeb3b"), 2))
        los.setZValue(1)

    def set_tokens(self, positions: list[tuple[float, float]], labels: list[str], movable: bool,
                   on_moved: Callable[[int], None], on_selected: Callable[[int], None]) -> None:
        for token in self.tokens.values():
            self.removeItem(token)
        self.tokens.clear()
        for slot, ((x_cm, z_cm), label) in enumerate(zip(positions, labels)):
            token = PlayerToken(slot, label, movable, on_moved, on_selected)
            token.setPos(to_scene(x_cm, z_cm))
            self.addItem(token)
            self.tokens[slot] = token

    def highlight(self, slot: int | None) -> None:
        for s, token in self.tokens.items():
            token.setBrush(QBrush(QColor("#ffcc80") if s == slot else QColor("#f3e7c8")))

    def clear_art(self) -> None:
        for item in self.art_items:
            self.removeItem(item)
        self.art_items.clear()

    def draw_art(self, segments: list[codec.ArtSegment], color: QColor) -> None:
        styles = {"solid": Qt.SolidLine, "dashed": Qt.DashLine, "zone": Qt.DashDotLine, "man": Qt.DotLine, "block": Qt.SolidLine}
        for seg in segments:
            pen = QPen(color, 2.2, styles.get(seg.style, Qt.SolidLine))
            pen.setCosmetic(True)
            pts = [to_scene(x, y) for x, y in seg.points]
            for a, b in zip(pts, pts[1:]):
                self.art_items.append(self.addLine(a.x(), a.y(), b.x(), b.y(), pen))
            if len(pts) >= 2:
                end = pts[-1]
                prev = pts[-2]
                if seg.end_marker == "arrow" or (seg.end_marker == "" and seg.style == "solid" and False):
                    ang = math.atan2(end.y() - prev.y(), end.x() - prev.x())
                    size = 7.0
                    poly = QPolygonF([
                        end,
                        QPointF(end.x() - size * math.cos(ang - 0.5), end.y() - size * math.sin(ang - 0.5)),
                        QPointF(end.x() - size * math.cos(ang + 0.5), end.y() - size * math.sin(ang + 0.5)),
                    ])
                    self.art_items.append(self.addPolygon(poly, pen, QBrush(color)))
                elif seg.end_marker == "block" or seg.style == "block":
                    ang = math.atan2(end.y() - prev.y(), end.x() - prev.x()) + math.pi / 2
                    size = 6.0
                    self.art_items.append(self.addLine(
                        end.x() - size * math.cos(ang), end.y() - size * math.sin(ang),
                        end.x() + size * math.cos(ang), end.y() + size * math.sin(ang), pen))
                elif seg.end_marker == "branch":
                    poly = QPolygonF([QPointF(end.x(), end.y() - 6), QPointF(end.x() + 6, end.y()),
                                      QPointF(end.x(), end.y() + 6), QPointF(end.x() - 6, end.y())])
                    marker = self.addPolygon(poly, pen)
                    marker.setToolTip(seg.label)
                    self.art_items.append(marker)
                    text = self.addSimpleText("Branch")
                    text.setBrush(QBrush(color)); text.setPos(end.x() + 7, end.y())
                    text.setToolTip(seg.label); self.art_items.append(text)
                elif seg.end_marker == "zone":
                    self.art_items.append(self.addEllipse(end.x() - 14, end.y() - 14, 28, 28, pen))
                elif seg.end_marker == "man":
                    self.art_items.append(self.addEllipse(end.x() - 4, end.y() - 4, 8, 8, pen, QBrush(color)))


class FieldView(QGraphicsView):
    def __init__(self, scene: QGraphicsScene):
        super().__init__(scene)
        self.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setMinimumSize(560, 520)

    def wheelEvent(self, event):
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.scale(factor, factor)


# ---------------------------------------------------------------------------
# Formation designer
# ---------------------------------------------------------------------------

PRESETS: dict[str, dict[int, tuple[float, float]]] = {
    "Pistol (QB 4 yd, HB 7 yd behind)": {0: (0, -4 * YD), 10: (0, -7 * YD)},
    "Shotgun (QB 5 yd, HB beside)": {0: (0, -5 * YD), 10: (-1.5 * YD, -5 * YD)},
    "Under center (QB 2 yd, HB 7 yd)": {0: (5, -185), 10: (0, -7 * YD)},
    "Wildcat (HB in the gun spot, QB flanked wide right)": {10: (0, -5 * YD), 0: (16 * YD, -1 * YD)},
}


class FormationDesignerDialog(QDialog):
    def __init__(self, book: Nfl2k5Playbook, body: bytes, formation_index: int, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(f"Formation Designer — from {book.formations[formation_index].name}")
        self.book = book
        self.body = body
        self.donor_index = formation_index
        self.record = formation_record(body, formation_index)
        self.category_index = formation_category_index(body, formation_index)
        self.positions: list[list[float]] = [[float(s.x[0]), float(s.z[0])] for s in self.record.slots]
        self.result_payload: dict | None = None
        self.offense = is_offense_formation(self.record)
        self._updating = False
        self._build()
        self._refresh_tokens()
        self._refresh_legality()

    # -- ui
    def _build(self) -> None:
        root = QHBoxLayout(self)
        self.scene = FieldScene(self.offense)
        self.view = FieldView(self.scene)
        root.addWidget(self.view, 3)
        side = QVBoxLayout()
        root.addLayout(side, 2)
        form = QFormLayout()
        self.name_edit = QLineEdit()
        self.name_edit.setMaxLength(40)
        self.name_edit.setPlaceholderText("Name (up to 40 ASCII characters; blank keeps the source name)")
        form.addRow("Name", self.name_edit)
        self.category_combo = QComboBox()
        for c in self.book.categories:
            self.category_combo.addItem(f"{c.name}  ({', '.join(codec.position_label(p) for p in category_positions(self.body, c.index))})", c.index)
        self.category_combo.setCurrentIndex(self.category_index)
        self.category_combo.currentIndexChanged.connect(self._category_changed)
        form.addRow("Personnel", self.category_combo)
        side.addLayout(form)
        presets = QHBoxLayout()
        for label, moves in PRESETS.items():
            button = QPushButton(label.split(" (")[0])
            button.setToolTip(label)
            button.clicked.connect(lambda _c=False, m=moves: self._apply_preset(m))
            presets.addWidget(button)
        flip = QPushButton("Flip L/R")
        flip.clicked.connect(self._flip)
        presets.addWidget(flip)
        side.addLayout(presets)
        self.table = QTableWidget(11, 4)
        self.table.setHorizontalHeaderLabels(["Slot", "Position", "X (yd, + right)", "Depth (yd, − behind LOS)"])
        self.table.verticalHeader().setVisible(False)
        for slot in range(11):
            self.table.setItem(slot, 0, QTableWidgetItem(str(slot)))
            self.table.setItem(slot, 1, QTableWidgetItem(""))
            for col in (2, 3):
                spin = QDoubleSpinBox()
                spin.setRange(-40.0, 40.0)
                spin.setDecimals(2)
                spin.setSingleStep(0.25)
                spin.valueChanged.connect(lambda _v, s=slot: self._table_changed(s))
                self.table.setCellWidget(slot, col, spin)
        self.table.resizeColumnsToContents()
        side.addWidget(self.table, 1)
        self.legality = QListWidget()
        self.legality.setMaximumHeight(120)
        side.addWidget(QLabel("NFL alignment check"))
        side.addWidget(self.legality)
        self.allow_illegal = QCheckBox("Allow an illegal formation anyway")
        side.addWidget(self.allow_illegal)
        self.alignment_label = QLabel("")
        side.addWidget(self.alignment_label)
        note = QLabel("Drag players on the field (snaps to ¼ yard) or type coordinates. The game reads these exact "
                      "centimetre positions when it lines the team up; mirror partners are recomputed for flipped plays. "
                      "Wildcat tip: after staging, design the play so the C's “Snap To” targets the back's slot and give "
                      "that back a Start (role Ball handler) + Ball Action (take snap) chain.")
        note.setWordWrap(True)
        side.addWidget(note)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Add formation to project")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        side.addWidget(buttons)

    # -- state
    def _labels(self) -> list[str]:
        return [codec.position_label(p) for p in category_positions(self.body, self.category_index)]

    def _refresh_tokens(self) -> None:
        self._updating = True
        labels = self._labels()
        self.scene.set_tokens([(x, z) for x, z in self.positions], labels, True, self._token_moved, lambda _s: None)
        for slot in range(11):
            self.table.item(slot, 1).setText(labels[slot])
            self.table.cellWidget(slot, 2).setValue(self.positions[slot][0] / YD)
            self.table.cellWidget(slot, 3).setValue(self.positions[slot][1] / YD)
        self._updating = False

    def _token_moved(self, slot: int) -> None:
        x_cm, z_cm = from_scene(self.scene.tokens[slot].pos())
        self.positions[slot] = [x_cm, z_cm]
        self._updating = True
        self.table.cellWidget(slot, 2).setValue(x_cm / YD)
        self.table.cellWidget(slot, 3).setValue(z_cm / YD)
        self._updating = False
        self._refresh_legality()

    def _table_changed(self, slot: int) -> None:
        if self._updating:
            return
        x = self.table.cellWidget(slot, 2).value() * YD
        z = self.table.cellWidget(slot, 3).value() * YD
        self.positions[slot] = [x, z]
        self.scene.tokens[slot].setPos(to_scene(x, z))
        self._refresh_legality()

    def _category_changed(self, _index: int) -> None:
        self.category_index = int(self.category_combo.currentData())
        self._refresh_tokens()
        self._refresh_legality()

    def _apply_preset(self, moves: dict[int, tuple[float, float]]) -> None:
        for slot, (x, z) in moves.items():
            self.positions[slot] = [x, z]
        self._refresh_tokens()
        self._refresh_legality()

    def _flip(self) -> None:
        for pos in self.positions:
            pos[0] = -pos[0]
        self._refresh_tokens()
        self._refresh_legality()

    def _current_slots(self) -> list[codec.FormationSlot]:
        return [codec.FormationSlot(0, codec.NO_MIRROR, 3, [int(round(x))] * 3, [int(round(z))] * 3) for x, z in self.positions]

    def _refresh_legality(self) -> None:
        self.legality.clear()
        issues = codec.formation_legality(self._current_slots(), category_positions(self.body, self.category_index), self.offense)
        if not issues:
            item = QListWidgetItem("Legal alignment ✔")
            item.setForeground(QBrush(QColor("#2e7d32")))
            self.legality.addItem(item)
        for issue in issues:
            item = QListWidgetItem(issue)
            item.setForeground(QBrush(QColor("#c62828")))
            self.legality.addItem(item)
        self._issues = issues
        if self.offense and self.record.type_code < 4:
            shotgun = self.positions[0][1] <= codec.SHOTGUN_DEPTH_THRESHOLD_CM
            self.alignment_label.setText(
                "QB alignment flag on Build: " + ("SHOTGUN snap (QB deeper than 2.7 yd)" if shotgun else "under-center snap")
            )

    def _accept(self) -> None:
        if self._issues and not self.allow_illegal.isChecked():
            QMessageBox.warning(self, "Illegal formation", "Fix the alignment issues or tick “Allow an illegal formation anyway”.")
            return
        name = self.name_edit.text().strip() or None
        self.result_payload = {
            "custom_name": name,
            "slot_positions": [[int(round(x)), int(round(z))] for x, z in self.positions],
            "category_index": self.category_index if self.category_index != formation_category_index(self.body, self.donor_index) else None,
        }
        self.accept()


# ---------------------------------------------------------------------------
# Play designer
# ---------------------------------------------------------------------------

@dataclass
class RouteRecipe:
    label: str
    build: Callable[[float, int], list[tuple[int, list[float]]]]
    hint: str


def _seg(kind: int, dist_yd: float, flag: int = 0) -> tuple[int, list[float]]:
    return (0x12, [kind, flag, dist_yd * YD, 15])


ROUTE_RECIPES: list[RouteRecipe] = [
    RouteRecipe("Go / Streak", lambda d, s: [_seg(0, d)], "straight downfield"),
    RouteRecipe("Slant", lambda d, s: [_seg(0, 3), _seg(1, d)], "3 yd then 30° inside break"),
    RouteRecipe("Out", lambda d, s: [_seg(0, d), _seg(5, 8)], "depth then 8 yd to the sideline"),
    RouteRecipe("In / Dig", lambda d, s: [_seg(0, d), _seg(4, 8)], "depth then 8 yd across"),
    RouteRecipe("Post / Corner (45° toward middle)", lambda d, s: [_seg(0, d), _seg(2, 10)], "depth then 45° break inside"),
    RouteRecipe("Corner / Post (45° away)", lambda d, s: [_seg(0, d), _seg(6, 10)], "depth then 45° break outside"),
    RouteRecipe("Curl / Stop", lambda d, s: [_seg(0, d), _seg(7, 2)], "depth then come back inside"),
    RouteRecipe("Comeback", lambda d, s: [_seg(0, d), _seg(11, 2)], "depth then come back outside"),
    RouteRecipe("Hitch", lambda d, s: [_seg(0, 5), _seg(7, 1)], "5 yd hitch"),
    RouteRecipe("Flat (lateral out)", lambda d, s: [_seg(5, d)], "run to the flat"),
    RouteRecipe("Drag (lateral in)", lambda d, s: [_seg(4, d)], "shallow cross"),
    RouteRecipe("Pass block (stay in)", lambda d, s: [_seg(9, 21 * s)], "back stays in to block"),
    RouteRecipe("Chip then release", lambda d, s: [_seg(8, 4), _seg(0, d)], "chip the end, then release"),
]

BLOCK_RECIPES: list[RouteRecipe] = [
    RouteRecipe("Run block (drive)", lambda d, s: [(0x11, [0, 0, 1, 0, 2, 0, 1 * YD, 0])], "drive block 1 yd upfield"),
    RouteRecipe("Pass set", lambda d, s: [(0x11, [1, 0, 1, 1, 2, 0, -1 * YD, 0])], "set 1 yd back"),
    RouteRecipe("Lead block (backs)", lambda d, s: [(0x11, [4, 0, 0, 0, 2, 0, d * YD, 1])], "lead through the hole"),
    RouteRecipe("Release and stalk block", lambda d, s: [(0x11, [3, 0, 1, 0, 2, 0, d * YD, 1])], "release downfield, then block"),
]

DEFENSE_RECIPES: list[RouteRecipe] = [
    RouteRecipe("Rush lane (line)", lambda d, s: [(0x1B, [0, 0, 0, 0, 17, 0]), (0x0B, [1, 8 + int(s * 3), 0])], "pass rush through a gap"),
    RouteRecipe("Man coverage (LB, 3 yd cushion)", lambda d, s: [(0x1B, [2, 0, 0, 4 * YD, 17, 0]), (0x0E, [0, 3 * YD, 0, 0, 0, 0, 0, 0])], "man on the assigned receiver"),
    RouteRecipe("Man coverage (DB, 2 yd cushion)", lambda d, s: [(0x1B, [2, 0, 0, 2 * YD, 17, 0]), (0x0E, [0, 2 * YD, 0, 13, 0, 0, 0, 0])], "press-ish man"),
    RouteRecipe("Deep half zone", lambda d, s: [(0x1B, [0, 0, 0, 0, 17, 1]), (0x0D, [12 * YD * s, 18 * YD, 10 if s > 0 else 7, 9 if s > 0 else 6, 11, 0, 0])], "deep half"),
    RouteRecipe("Hook / curl zone", lambda d, s: [(0x1B, [2, 0, 0, 4 * YD, 17, 1]), (0x0D, [6 * YD * s, 10 * YD, 10 if s > 0 else 7, 9 if s > 0 else 6, 4, 0, 0])], "underneath zone"),
    RouteRecipe("Flat zone", lambda d, s: [(0x1B, [2, 0, 0, 4 * YD, 17, 1]), (0x0D, [15 * YD * s, 5 * YD, 10 if s > 0 else 7, 9 if s > 0 else 6, 5 if s > 0 else 6, 0, 0])], "flat zone"),
]


class PlayDesignerDialog(QDialog):
    def __init__(self, book: Nfl2k5Playbook, body: bytes, formation_index: int, donor_play_index: int,
                 formation_positions: list[tuple[int, int]] | None = None, formation_name: str | None = None,
                 category_index: int | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.book = book
        self.body = body
        self.formation_index = formation_index
        self.donor_play_index = donor_play_index
        self.record = formation_record(body, formation_index)
        if formation_positions is not None:
            for slot, (x, z) in enumerate(formation_positions):
                self.record.set_position(slot, x, z)
        self.category_index = category_index if category_index is not None else formation_category_index(body, formation_index)
        self.position_codes = category_positions(body, self.category_index)
        self.play_flags, self.donor_chains = play_chains(body, donor_play_index)
        self.family = (self.play_flags >> 6) & 7
        self.chains: list[list[codec.Node]] = [[codec.Node.from_bytes(n) for n in nodes] for _d, nodes in self.donor_chains]
        self.changed: list[bool] = [False] * 11
        self.spy_slots: set[int] = set()
        self.current_slot = 5 if self.family == 1 else 6
        self.current_node: int | None = None
        self.result_payload: dict | None = None
        self.setWindowTitle(f"Play Designer — {book.plays[donor_play_index].name} in {formation_name or book.formations[formation_index].name}")
        self._build()
        self._refresh_slots()
        self._select_slot(self.current_slot)
        self._refresh_art()
        self._validate()

    # -- ui
    def _build(self) -> None:
        root = QVBoxLayout(self)
        top = QHBoxLayout()
        self.name_edit = QLineEdit()
        self.name_edit.setMaxLength(40)
        self.name_edit.setPlaceholderText("Custom play name (printable ASCII, ≤40) — blank reuses the donor name")
        top.addWidget(QLabel("Name"))
        top.addWidget(self.name_edit, 1)
        fam = codec_family_label(self.family)
        top.addWidget(QLabel(f"Family: {fam}   Donor: {self.book.plays[self.donor_play_index].name}"))
        root.addLayout(top)
        body = QHBoxLayout()
        root.addLayout(body, 1)
        self.scene = FieldScene(self.family in (0, 2, 4, 6))
        self.view = FieldView(self.scene)
        body.addWidget(self.view, 3)
        mid = QVBoxLayout()
        body.addLayout(mid, 2)
        mid.addWidget(QLabel("Players (slots)"))
        self.slot_list = QListWidget()
        self.slot_list.currentRowChanged.connect(self._select_slot)
        mid.addWidget(self.slot_list, 2)
        mid.addWidget(QLabel("Nodes of the selected player"))
        self.node_list = QListWidget()
        self.node_list.currentRowChanged.connect(self._select_node)
        mid.addWidget(self.node_list, 2)
        node_buttons = QHBoxLayout()
        self.add_opcode = QComboBox()
        for op in range(codec.OPCODE_COUNT):
            if op == 0x19:
                continue
            self.add_opcode.addItem(f"{op:#04x} {codec.OPCODE_NAMES.get(op, '')}", op)
        self.add_opcode.setCurrentIndex(self.add_opcode.findData(0x12))
        node_buttons.addWidget(self.add_opcode, 1)
        for label, handler in (("Add", self._add_node), ("Remove", self._remove_node), ("▲", self._node_up), ("▼", self._node_down), ("Reset slot", self._reset_slot)):
            button = QPushButton(label)
            button.clicked.connect(handler)
            node_buttons.addWidget(button)
        mid.addLayout(node_buttons)
        right = QVBoxLayout()
        body.addLayout(right, 2)
        quick = QGroupBox("Quick builders (replace this player's assignment)")
        quick_form = QFormLayout(quick)
        self.route_combo = QComboBox()
        for recipe in ROUTE_RECIPES:
            self.route_combo.addItem(recipe.label, recipe)
        self.depth_spin = QDoubleSpinBox()
        self.depth_spin.setRange(1, 40)
        self.depth_spin.setValue(10)
        self.depth_spin.setSuffix(" yd")
        route_row = QHBoxLayout()
        route_row.addWidget(self.route_combo, 1)
        route_row.addWidget(self.depth_spin)
        route_button = QPushButton("Route")
        route_button.clicked.connect(lambda: self._apply_recipe(self.route_combo.currentData(), self.depth_spin.value()))
        route_row.addWidget(route_button)
        quick_form.addRow("Receiver route", route_row)
        self.block_combo = QComboBox()
        for recipe in BLOCK_RECIPES:
            self.block_combo.addItem(recipe.label, recipe)
        block_row = QHBoxLayout()
        block_row.addWidget(self.block_combo, 1)
        block_button = QPushButton("Block")
        block_button.clicked.connect(lambda: self._apply_recipe(self.block_combo.currentData(), self.depth_spin.value()))
        block_row.addWidget(block_button)
        quick_form.addRow("Blocking", block_row)
        self.defense_combo = QComboBox()
        if self.family == 1:
            for label, key in DEFENSE_ASSIGNMENT_CHOICES:
                self.defense_combo.addItem(label, key)
        else:
            for recipe in DEFENSE_RECIPES:
                self.defense_combo.addItem(recipe.label, recipe)
        def_row = QHBoxLayout()
        def_row.addWidget(self.defense_combo, 1)
        def_button = QPushButton("Defense")
        def_button.clicked.connect(self._edit_defense if self.family == 1 else lambda: self._apply_recipe(self.defense_combo.currentData(), self.depth_spin.value()))
        def_row.addWidget(def_button)
        quick_form.addRow("Coverage / rush", def_row)
        right.addWidget(quick)
        if self.family == 1:
            warning = QLabel(lib.DEFENSE_EVIDENCE + ". " + lib.SPY_NOTICE)
            warning.setWordWrap(True)
            right.addWidget(warning)
            presets = QComboBox()
            for preset in lib.DEFENSE_PRESETS:
                presets.addItem(preset)
            right.addWidget(presets)
            apply_preset = QPushButton("Apply defense preset")
            apply_preset.clicked.connect(lambda: self._defense_preset(presets.currentText()))
            right.addWidget(apply_preset)
        self.editor_box = QGroupBox("Selected node")
        self.editor_form = QFormLayout(self.editor_box)
        self.opcode_label = QLabel("—")
        self.editor_form.addRow("Opcode", self.opcode_label)
        self.operand_widgets: list[tuple[codec.OperandSpec, QWidget]] = []
        right.addWidget(self.editor_box, 1)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        right.addWidget(self.status)
        self.link_check = QCheckBox("Show this play in the formation's menu")
        self.link_check.setChecked(True)
        right.addWidget(self.link_check)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Add play to project")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        right.addWidget(buttons)

    # -- helpers
    def _positions(self) -> list[tuple[float, float]]:
        return [(float(s.x[0]), float(s.z[0])) for s in self.record.slots]

    def _labels(self) -> list[str]:
        return [codec.position_label(p) for p in self.position_codes]

    def _refresh_slots(self) -> None:
        row = self.slot_list.currentRow()
        self.slot_list.blockSignals(True)
        self.slot_list.clear()
        for slot in range(11):
            summary = " → ".join(n.name for n in self.chains[slot])
            mark = "✎ " if self.changed[slot] else ""
            self.slot_list.addItem(f"{mark}{slot}: {self._labels()[slot]} — {summary}")
        if row >= 0:
            self.slot_list.setCurrentRow(row)
        self.slot_list.blockSignals(False)
        self.scene.set_tokens(self._positions(), self._labels(), False, lambda _s: None, self._select_slot_from_token)

    def _select_slot_from_token(self, slot: int) -> None:
        self.slot_list.setCurrentRow(slot)

    def _select_slot(self, slot: int) -> None:
        if slot < 0:
            return
        self.current_slot = slot
        self.scene.highlight(slot)
        self.node_list.blockSignals(True)
        self.node_list.clear()
        for node in self.chains[slot]:
            self.node_list.addItem(node.describe())
        self.node_list.blockSignals(False)
        self.node_list.setCurrentRow(len(self.chains[slot]) - 1 if self.chains[slot] else -1)
        self._select_node(self.node_list.currentRow())

    def _select_node(self, index: int) -> None:
        for spec, widget in self.operand_widgets:
            label = self.editor_form.labelForField(widget)
            self.editor_form.removeWidget(widget)
            widget.hide()
            widget.deleteLater()
            if label is not None:
                self.editor_form.removeWidget(label)
                label.hide()
                label.deleteLater()
        self.operand_widgets.clear()
        self.current_node = index if index >= 0 else None
        if self.current_node is None or self.current_node >= len(self.chains[self.current_slot]):
            self.opcode_label.setText("—")
            return
        node = self.chains[self.current_slot][self.current_node]
        self.opcode_label.setText(f"{node.op:#04x} {node.name}   (flags {node.flags:#04x})")
        for k, spec in enumerate(codec.OPERAND_SCHEMAS.get(node.op, ())):
            value = node.operands[k] if k < len(node.operands) else 0
            if spec.kind in ("x_ft", "y_ft"):
                w = QDoubleSpinBox()
                w.setRange(-64, 64)
                w.setDecimals(2)
                w.setSingleStep(0.5)
                w.setSuffix(" yd")
                w.setValue(value / YD)
                w.valueChanged.connect(lambda v, kk=k: self._operand_changed(kk, v * YD))
            elif spec.kind == "time":
                w = QDoubleSpinBox()
                w.setRange(0, 6.3)
                w.setSingleStep(0.1)
                w.setSuffix(" s")
                w.setValue(value)
                w.valueChanged.connect(lambda v, kk=k: self._operand_changed(kk, v))
            elif spec.kind == "angle":
                w = QSpinBox()
                w.setRange(-30, 63)
                w.setSingleStep(3)
                w.setValue(int(value))
                w.valueChanged.connect(lambda v, kk=k: self._operand_changed(kk, v))
            elif spec.choices:
                w = QComboBox()
                for code, label in spec.choices.items():
                    w.addItem(f"{code}: {label}", code)
                if w.findData(int(value)) < 0:
                    w.addItem(f"{int(value)}", int(value))
                w.setCurrentIndex(w.findData(int(value)))
                w.currentIndexChanged.connect(lambda _i, kk=k, ww=w: self._operand_changed(kk, ww.currentData()))
            else:
                w = QSpinBox()
                top = (1 << spec.bits) - 1 if spec.bits else 0
                if spec.kind == "lane":
                    top = 17
                w.setRange(0, max(top, int(value)))
                w.setValue(int(value))
                w.valueChanged.connect(lambda v, kk=k: self._operand_changed(kk, v))
            # the spin box shows yards (the codec stores feet); the caption must say the same unit
            caption = spec.label.replace("(ft", "(yd") if spec.kind in ("x_ft", "y_ft") else spec.label
            self.editor_form.addRow(caption, w)
            self.operand_widgets.append((spec, w))

    def _operand_changed(self, k: int, value: float) -> None:
        if self.current_node is None:
            return
        node = self.chains[self.current_slot][self.current_node]
        while len(node.operands) <= k:
            node.operands.append(0)
        node.operands[k] = value
        self.changed[self.current_slot] = True
        # Never rebuild the operand form from inside one of its own widget signals:
        # the emitting widget would be deleted while still on the call stack.
        self.node_list.item(self.current_node).setText(node.describe())
        self._refresh_slot_labels()
        self._refresh_art()
        self._validate()

    def _refresh_slot_labels(self) -> None:
        for slot in range(11):
            item = self.slot_list.item(slot)
            if item is None:
                continue
            summary = " → ".join(n.name for n in self.chains[slot])
            mark = "✎ " if self.changed[slot] else ""
            item.setText(f"{mark}{slot}: {self._labels()[slot]} — {summary}")

    def _mark_changed(self) -> None:
        self.spy_slots.discard(self.current_slot)
        self.changed[self.current_slot] = True
        self._refresh_slot_labels()
        self._refresh_art()
        self._validate()

    def _add_node(self) -> None:
        op = int(self.add_opcode.currentData())
        specs = codec.OPERAND_SCHEMAS.get(op, ())
        node = codec.Node(op, 0, [0.0] * len(specs))
        if op == 0x12:
            node.operands = [0, 0, 10 * YD, 15]
        elif op == 0x01:
            node.operands = [1, 3, 0, 0.0, 0.0, 0.0]
        chain = self.chains[self.current_slot]
        at = (self.current_node + 1) if self.current_node is not None else len(chain)
        chain.insert(at, node)
        self.changed[self.current_slot] = True
        self._select_slot(self.current_slot)
        self.node_list.setCurrentRow(at)
        self._mark_changed()

    def _remove_node(self) -> None:
        chain = self.chains[self.current_slot]
        if self.current_node is None or len(chain) <= 1:
            return
        del chain[self.current_node]
        self._select_slot(self.current_slot)
        self._mark_changed()

    def _node_up(self) -> None:
        chain = self.chains[self.current_slot]
        i = self.current_node
        if i is None or i <= 0:
            return
        chain[i - 1], chain[i] = chain[i], chain[i - 1]
        self._select_slot(self.current_slot)
        self.node_list.setCurrentRow(i - 1)
        self._mark_changed()

    def _node_down(self) -> None:
        chain = self.chains[self.current_slot]
        i = self.current_node
        if i is None or i >= len(chain) - 1:
            return
        chain[i + 1], chain[i] = chain[i], chain[i + 1]
        self._select_slot(self.current_slot)
        self.node_list.setCurrentRow(i + 1)
        self._mark_changed()

    def _reset_slot(self) -> None:
        self.spy_slots.discard(self.current_slot)
        self.chains[self.current_slot] = [codec.Node.from_bytes(n) for n in self.donor_chains[self.current_slot][1]]
        self.changed[self.current_slot] = False
        self._select_slot(self.current_slot)
        self._refresh_slots()
        self._refresh_art()
        self._validate()

    def _apply_recipe(self, recipe: RouteRecipe, depth: float) -> None:
        slot = self.current_slot
        side = 1 if self.record.slots[slot].x[0] >= 0 else -1
        nodes = [codec.Node(op, 0, list(vals)) for op, vals in recipe.build(depth, side)]
        keep: list[codec.Node] = []
        donor = self.chains[slot]
        if nodes and nodes[0].op != 0x1B:
            # keep the retail opener (Start, and Snap To for the snapper) so the chain stays legal
            for node in donor:
                if node.op in (0x01, 0x02, 0x03):
                    keep.append(codec.Node(node.op, 0, list(node.operands)))
                else:
                    break
            if not keep:
                keep = [codec.Node(0x01, 0, [1, 3, 0, 0.0, 0.0, 0.0])]
        self.chains[slot] = keep + nodes
        self.changed[slot] = True
        self._select_slot(slot)
        self._mark_changed()

    def _defense_design(self):
        front, _ = lib.defense_donors(self.book, self.body, self.formation_index)
        return lib.DefenseDesign(self.formation_index, front, self.donor_play_index, self.play_flags,
                                 [[(n.op, list(n.operands)) for n in c] for c in self.chains],
                                 lib.decoded_chains(self.body, front), set(self.spy_slots))

    def _take_defense_design(self, design):
        self.donor_play_index = design.donor_play_index
        self.play_flags, self.donor_chains = lib.play_chains(self.body, design.donor_play_index)
        self.chains = [[codec.Node(op, 0, list(v)) for op, v in c] for c in design.chains]
        self.changed = [True] * 11
        self.spy_slots = set(design.spy_slots)
        self._refresh_slots(); self._select_slot(self.current_slot); self._refresh_art(); self._validate()

    def _edit_defense(self):
        try:
            design = self._defense_design()
            if edit_defense_assignment(self, design, self.book, self.body, self.current_slot, self.defense_combo.currentData()):
                self._take_defense_design(design)
        except ValueError as exc:
            QMessageBox.warning(self, "Defense", str(exc))

    def _defense_preset(self, name):
        try:
            design = lib.make_defense_design(self.book, self.body, self.formation_index, name)
            if name == "Double A Show EXPERIMENTAL":
                positions = lib.double_a_positions(self.book, self.body, self.formation_index)
                if self._positions() != positions:
                    raise ValueError("Create a separate Double A formation in Create a Play first")
            self._take_defense_design(design)
        except ValueError as exc:
            QMessageBox.warning(self, "Defense", str(exc))

    # -- art + validation
    def _assignments_bytes(self) -> list[tuple[int, list[bytes]]]:
        out: list[tuple[int, list[bytes]]] = []
        for slot in range(11):
            donor_desc, donor_nodes = self.donor_chains[slot]
            if not self.changed[slot]:
                out.append((donor_desc, list(donor_nodes)))
                continue
            nodes = [codec.Node(n.op, n.flags, list(n.operands)) for n in self.chains[slot]]
            codec.assign_node_flags(nodes)
            out.append((donor_desc, [n.to_bytes() for n in nodes]))
        for slot in range(11):
            if self.changed[slot]:
                desc = codec.build_descriptor(self.play_flags, out, slot, self.donor_chains[slot][0] >> 24)
                out[slot] = (desc, out[slot][1])
        return out

    def _refresh_art(self) -> None:
        if self.family == 1:
            try:
                draw_defense_design(self.scene, self._defense_design(), self._positions())
                return
            except ValueError:
                pass
        self.scene.clear_art()
        positions = self._positions()
        palette = [QColor("#ffffff"), QColor("#ffd54f"), QColor("#80deea"), QColor("#f48fb1")]
        for slot in range(11):
            x0, z0 = positions[slot]
            side = 1 if x0 >= 0 else -1
            segs = codec.play_art(self.chains[slot], (x0, z0), side=side, wide_left=x0 < 0)
            color = palette[0] if not self.changed[slot] else palette[1]
            if slot == self.current_slot:
                color = palette[2]
            self.scene.draw_art(segs, color)

    def _validate(self) -> str | None:
        try:
            if self.family == 1:
                for slot in range(11):
                    if self.changed[slot]:
                        codec.validate_defense_operands([(n.op, n.operands) for n in self.chains[slot]])
            assignments = self._assignments_bytes()
            codec.validate_sync(assignments)
            error = codec.validate_play(self.play_flags, assignments)
            if sum(len(c) for c, changed in zip(self.chains, self.changed) if changed) > 3500 - self.book.node_count:
                error = "Cloned chains exceed the remaining node pool"
        except Exception as exc:  # noqa: BLE001 - surfaced to the user
            error = f"cannot encode: {exc}"
        if error:
            self.status.setText(f"✖ The game would refuse this play: {error}")
            self.status.setStyleSheet("color:#c62828")
        else:
            count = sum(len(c) for c, changed in zip(self.chains, self.changed) if changed)
            self.status.setText(f"Structure check passed. Cloned nodes {count}; pool {count * 8} bytes. "
                                + (lib.DEFENSE_EVIDENCE if self.family == 1 else "Test in-game."))
            self.status.setStyleSheet("color:#2e7d32")
        self._error = error
        return error

    def _accept(self) -> None:
        if self._validate():
            QMessageBox.warning(self, "Play rejected", self._error)
            return
        if not any(self.changed):
            QMessageBox.information(self, "Nothing changed", "Change at least one player's assignment, or use Create Play for a plain clone.")
            return
        assignments = []
        for slot in range(11):
            if not self.changed[slot]:
                assignments.append(None)
            else:
                assignments.append(codec.chain_json(codec.authored_chain(self.chains[slot])))
        self.result_payload = {
            "custom_name": self.name_edit.text().strip() or None,
            "donor_play_index": self.donor_play_index,
            "assignments": assignments,
            "link": self.link_check.isChecked(),
            "play_flags": self._class_flags(),
            "spy_intent": {"schema": lib.SPY_INTENT_SCHEMA, "slots": sorted(self.spy_slots)},
        }
        self.accept()

    def _class_flags(self) -> int | None:
        """Header flags for the staged play, or None to keep the donor's.

        The game plays a play as the CLASS in its header (0x6000 pass / 0x8000 run), not as
        what the QB's chain does.  When the authored QB chain changes shape (a run donor
        turned into a dropback pass, or the reverse) the class follows the new chain, taken
        from a stock play of this book with the same shape."""
        if self.family != 0 or not self.changed[0]:
            return None
        import mod_editor.core.nfl2k5_play_library as lib

        new_sig = lib.qb_signature([(n.op, n.operands) for n in self.chains[0]])
        old_sig = lib.qb_signature(self.donor_chains[0][1])
        if new_sig == old_sig or new_sig == "other":
            return None
        play_type = {"pass": "pass", "pa_pass": "pa_pass", "run": "run", "draw": "run", "qb_run": "keeper"}[new_sig]
        _donor, flags = lib.reference_play_for(self.book, self.body, play_type, "Draw" if new_sig == "draw" else None)
        return (flags & ~lib.PLAY_FLAGS_KEEP_MASK) | (self.play_flags & lib.PLAY_FLAGS_KEEP_MASK)


def codec_family_label(family: int) -> str:
    return ("Offense", "Defense", "Punt", "Punt return", "Field goal", "FG defense", "Kickoff", "Kick return")[family & 7]


__all__ = ["FormationDesignerDialog", "PlayDesignerDialog", "ROUTE_RECIPES", "BLOCK_RECIPES", "DEFENSE_RECIPES"]


DEFENSE_ASSIGNMENT_CHOICES = (
    ("Man coverage", "man"), ("Zone landmark", "zone"), ("Rush lane", "rush"),
    ("Retail paired exchange script", "exchange"), ("Spy", "spy"),
    ("Restore donor assignment", "inherited"),
)


def draw_defense_design(scene, design, positions, *, mirrored=False):
    """Effective front/coverage art, with separate authoring intent marks."""
    from mod_editor.core import nfl2k5_play_library as lib
    scene.clear_art()
    active = lib.defense_active(design.chains)
    for slot, chain in enumerate(design.effective()):
        start = positions[slot]
        segs = codec.play_art([codec.Node(op, 0, list(vals)) for op, vals in chain], start,
                              side=1 if start[0] >= 0 else -1)
        if mirrored:
            for segment in segs:
                segment.points = [(-x, z) for x, z in segment.points]
        scene.draw_art(segs, QColor('#ffd54f') if slot in active else QColor('#b0bec5'))
        if slot in design.spy_slots:
            mark = scene.addSimpleText("S: shallow zone")
            mark.setBrush(QBrush(QColor('#ff80ab')))
            mark.setPos(to_scene(-start[0] if mirrored else start[0], start[1] + YD))
            scene.art_items.append(mark)


def edit_defense_assignment(parent, design, book, body, slot, initial="zone"):
    from mod_editor.core import nfl2k5_play_library as lib
    dialog = QDialog(parent)
    dialog.setWindowTitle(f"Defender {slot}: {lib.defense_personnel(book, body, design.formation_index)['labels'][slot]}")
    form = QFormLayout(dialog)
    choices = QComboBox()
    for label, key in DEFENSE_ASSIGNMENT_CHOICES:
        choices.addItem(label, key)
    choices.setCurrentIndex(max(0, choices.findData(initial)))
    form.addRow("Assignment", choices)
    x = QDoubleSpinBox(); x.setRange(-26, 26); x.setSuffix(" yd")
    depth = QDoubleSpinBox(); depth.setRange(0, 40); depth.setValue(4 if initial == 'spy' else 8); depth.setSuffix(" yd")
    lane = QSpinBox(); lane.setRange(0, 17); lane.setValue(8)
    delay = QDoubleSpinBox(); delay.setRange(0, 6.3); delay.setSingleStep(.1); delay.setSuffix(" s")
    target = QSpinBox(); target.setRange(0, 14)
    cushion = QDoubleSpinBox(); cushion.setRange(0, 20); cushion.setValue(3); cushion.setSuffix(" yd")
    for label, widget in (("Zone lateral", x), ("Zone depth", depth), ("Rush lane (17 = none)", lane),
                          ("Rush delay", delay), ("Opponent selector (0 = automatic)", target), ("Man cushion", cushion)):
        form.addRow(label, widget)
    notice = QLabel(lib.DEFENSE_EVIDENCE + ". " + lib.SPY_NOTICE + ". Exchanges replace the whole paired script.")
    notice.setWordWrap(True); form.addRow(notice)
    error = QLabel(); error.setWordWrap(True); form.addRow(error)
    def changed():
        spy = choices.currentData() == 'spy'
        depth.setRange(3 if spy else 0, 5 if spy else 40)
        if spy:
            x.setValue(0)
        x.setEnabled(not spy)
    choices.currentIndexChanged.connect(changed)
    changed()
    buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    def accept():
        try:
            design.set_assignment(book, body, slot, choices.currentData(), x_yd=x.value(), depth_yd=depth.value(),
                                  lane=lane.value(), delay=delay.value(), target=target.value(), cushion_yd=cushion.value())
        except ValueError as exc:
            error.setText(str(exc)); return
        dialog.accept()
    buttons.accepted.connect(accept); buttons.rejected.connect(dialog.reject); form.addRow(buttons)
    return dialog.exec_() == dialog.Accepted
