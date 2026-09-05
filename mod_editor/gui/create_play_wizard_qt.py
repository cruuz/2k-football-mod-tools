"""Create a Play — the step-by-step playbook wizard for NFL 2K5.

Five steps a 12-year-old can follow: pick a team's playbook, lay out a formation
(templates, grid snapping, click a player to move or swap him), choose run or
pass, hand out assignments by clicking players, then finalize: the wizard
suggests outdated stock formations/plays to replace, stages everything through
the studio facade, and offers Build + Launch.  All football logic lives in
:mod:`mod_editor.core.nfl2k5_play_library`; every play is checked against the
ported retail validator before it can be staged.
"""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from PyQt5.QtCore import QPointF, Qt, QTimer
from PyQt5.QtGui import QBrush, QColor, QCursor, QFont, QPainterPath, QPen
from PyQt5.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout, QFrame,
    QGroupBox, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMenu,
    QMessageBox, QPushButton, QRadioButton, QScrollArea, QSizePolicy, QSpinBox, QStackedWidget,
    QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget, QWizard, QWizardPage,
)

from mod_editor.core import nfl2k5_play_codec as codec
from mod_editor.core import nfl2k5_play_library as lib
from mod_editor.core.nfl2k5_playbook_inspector import Nfl2k5Playbook
from mod_editor.gui.play_designer_qt import FieldScene, FieldView, PlayerToken, from_scene, to_scene

YD = codec.YD_CM
BIG = "font-size: 15px;"
HUGE = "font-size: 20px; font-weight: 600;"


def _quiet(*_args: object) -> None:
    pass


# ---------------------------------------------------------------------------
# QB read progression: the four ordered 1-5 values every Dropback node carries
# ---------------------------------------------------------------------------
# Opcode 0x06 ("Dropback / Pass") stores five small fields; operands 1-4 are four
# ordered values in 1..5 (171 distinct tuples over the 3,225 retail Dropback
# nodes) and are the quarterback's read order.  They are editable today and no
# retail play ever set them from this studio: a wizard play inherited whatever
# the generator hard-coded.  What the four numbers select *is* a reading of the
# corpus, not a witnessed runtime behaviour, so the wizard labels them "read
# order" and never claims more.

DROPBACK_OPCODE = 0x06
READ_ORDER_SLICE = slice(1, 5)
READ_ORDER_MIN, READ_ORDER_MAX = 1, 5


def read_order_of(chain: list) -> tuple[int, int, int, int] | None:
    """The four ordered values of a chain's Dropback node, or ``None`` when the
    chain has no Dropback node (a run, a sneak, a blocker)."""

    for op, vals in chain:
        if op == DROPBACK_OPCODE and len(vals) >= 5:
            return tuple(int(v) for v in vals[READ_ORDER_SLICE])  # type: ignore[return-value]
    return None


def with_read_order(chain: list, order: "tuple[int, ...] | list[int]", *, allow_zero: bool = False) -> list:
    """A copy of ``chain`` whose Dropback node carries ``order`` (four 1-5 values)."""

    values = [max(0 if allow_zero else READ_ORDER_MIN, min(READ_ORDER_MAX, int(v))) for v in order]
    if len(values) != 4:
        raise ValueError("a read order is four values")
    out = []
    for op, vals in chain:
        if op == DROPBACK_OPCODE and len(vals) >= 5:
            fresh = list(vals)
            fresh[READ_ORDER_SLICE] = values
            out.append((op, fresh))
        else:
            out.append((op, list(vals)))
    return out


#: Menu selection groups.  Every populated retail formation carries exactly one
#: link in each of groups 0, 1 and 2 (938 formations, no exceptions) -- the three
#: audible slots, the same structure proved in APF's SPLB.  Group 3 exists in the
#: format and is what the tutorial book uses.
AUDIBLE_GROUPS: tuple[tuple[str, object], ...] = (
    ("Inherit from the formation", None),
    ("Audible 1 (group 0)", 0),
    ("Audible 2 (group 1)", 1),
    ("Audible 3 (group 2)", 2),
    ("Group 3 (tutorial books)", 3),
)


@dataclass
class DesignedFormation:
    name: str
    category_index: int
    donor_formation_index: int
    positions: list[tuple[int, int]]
    kinds: list[int]
    labels: list[str]
    replace_index: int | None = None
    selector: str | None = None
    plays: list["DesignedPlay"] = field(default_factory=list)
    codes: list[int] = field(default_factory=list)           # eleven position codes (who lines up where)
    category_positions: list[int] | None = None              # codes written into the group when no stock group fits
    personnel_note: str = ""


@dataclass
class DesignedPlay:
    name: str
    play_type: str
    concept_or_scheme: str
    chains: list[lib.Chain]
    donor_play_index: int
    replace_index: int | None = None
    play_flags: int | None = None   # header class word (0x6000 pass / 0x8000 run) from a stock play of the same shape


class CreatePlayWizard(QWizard):
    """The whole flow.  ``host`` is the studio facade (playbook_raw_body, browse_playbooks, create_*, build_iso, launch_xemu)."""

    def __init__(self, host, parent: QWidget | None = None):
        super().__init__(parent)
        self.host = host
        self.setWindowTitle("Create a Play")
        self.setWizardStyle(QWizard.ModernStyle)
        self.setOption(QWizard.NoBackButtonOnStartPage, True)
        self.setOption(QWizard.HaveHelpButton, False)
        self.setMinimumSize(1380, 860)
        self.book: Nfl2k5Playbook | None = None
        self.body: bytes | None = None
        self.designed: list[DesignedFormation] = []
        self.current: DesignedFormation | None = None
        self._reference_cache: dict[tuple[str, str | None], tuple[int, int]] = {}
        self.page_team = TeamPage(self)
        self.page_formation = FormationPage(self)
        self.page_type = PlayTypePage(self)
        self.page_assign = AssignPage(self)
        self.page_finalize = FinalizePage(self)
        for page in (self.page_team, self.page_formation, self.page_type, self.page_assign, self.page_finalize):
            self.addPage(page)
        self.setButtonText(QWizard.FinishButton, "Close")

    # -- helpers
    def load_book(self, book: Nfl2k5Playbook) -> None:
        self.book = book
        self.body = self.host.playbook_raw_body(book.asset_id)
        self._reference_cache.clear()

    def reference_play(self, play_type: str, scheme: str | None = None) -> tuple[int, int]:
        """(donor play index, header flags) for a play of this type: a stock play of the same
        shape (dropback pass, play-action pass, handoff, draw, QB run).  The header flags
        carry the CLASS the game plays the play as; the first offensive play of a book is a
        run, and a pass staged under its header is played as a run (icons vanish, the QB
        cannot throw)."""
        assert self.book is not None and self.body is not None
        key = (play_type, scheme)
        if key not in self._reference_cache:
            self._reference_cache[key] = lib.reference_play_for(self.book, self.body, play_type, scheme)
        return self._reference_cache[key]

    def donor_play_for(self, play_type: str, scheme: str | None = None) -> int:
        return self.reference_play(play_type, scheme)[0]


# ---------------------------------------------------------------------------
# Step 1 — team
# ---------------------------------------------------------------------------

class TeamPage(QWizardPage):
    def __init__(self, wizard: CreatePlayWizard):
        super().__init__()
        self.wiz = wizard
        self.setTitle("Step 1 — Whose playbook are we changing?")
        self.setSubTitle("Pick the team you'll play as. Your new formations and plays go into that team's playbook.")
        layout = QVBoxLayout(self)
        self.list = QListWidget()
        self.list.setStyleSheet(HUGE)
        self.list.setSpacing(4)
        layout.addWidget(self.list, 1)
        self.status = QLabel("Load your NFL 2K5 disc first (File → Open), then the 37 playbooks appear here.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        # Somebody else already did the work: a community pack is the same recipe
        # this wizard produces, so it installs into the same edit list.
        self.pack_card = QGroupBox("Already have a playbook pack?")
        card = QVBoxLayout(self.pack_card)
        card_text = QLabel(
            "A playbook pack (.2k5book) is a set of formations and plays someone shared. It carries "
            "no game data; you will see exactly which stock entries it replaces before anything is added."
        )
        card_text.setWordWrap(True)
        card_text.setStyleSheet(BIG)
        card.addWidget(card_text)
        self.install_pack_button = QPushButton("Install a playbook pack…")
        self.install_pack_button.setStyleSheet(HUGE)
        self.install_pack_button.clicked.connect(self._install_pack)
        card.addWidget(self.install_pack_button)
        self.pack_status = QLabel("")
        self.pack_status.setWordWrap(True)
        card.addWidget(self.pack_status)
        layout.addWidget(self.pack_card)

        self.list.itemSelectionChanged.connect(self.completeChanged)
        self.list.itemDoubleClicked.connect(lambda _i: self.wiz.next())
        self._books: list[Nfl2k5Playbook] = []

    def _install_pack(self) -> None:
        from mod_editor.gui.playbook_pack_dialog_qt import (
            PlaybookPackInstallDialog, choose_pack_to_open,
        )

        path = choose_pack_to_open(self)
        if path is None:
            return
        try:
            dialog = PlaybookPackInstallDialog(self.wiz.host, path, self)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Install a playbook pack", str(exc))
            return
        if dialog.exec_() != dialog.Accepted:
            return
        self.pack_status.setText(getattr(dialog, "result_message", "Playbook pack staged."))

    def initializePage(self) -> None:
        self.list.clear()
        self._books = []
        try:
            books = list(self.wiz.host.browse_playbooks("", _quiet))
        except Exception as exc:  # noqa: BLE001
            self.status.setText(f"Playbooks are not available yet: {exc}")
            return
        for book in sorted(books, key=lambda b: b.book_name):
            item = QListWidgetItem(f"{book.book_name}   —   {len(book.formations)} formations, {len(book.plays)} plays")
            item.setData(Qt.UserRole, book.asset_id)
            self.list.addItem(item)
            self._books.append(book)
        self.status.setText("Tip: GEN, PRACTICE and Editor are utility playbooks, not NFL teams.")

    def isComplete(self) -> bool:
        return bool(self.list.selectedItems())

    def validatePage(self) -> bool:
        items = self.list.selectedItems()
        if not items:
            return False
        asset_id = items[0].data(Qt.UserRole)
        book = next(b for b in self._books if b.asset_id == asset_id)
        try:
            self.wiz.load_book(book)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Create a Play", str(exc))
            return False
        return True


# ---------------------------------------------------------------------------
# Step 2 — formation
# ---------------------------------------------------------------------------

class FormationPage(QWizardPage):
    def __init__(self, wizard: CreatePlayWizard):
        super().__init__()
        self.wiz = wizard
        self.setTitle("Step 2 — Line them up")
        self.setSubTitle("Start from a modern template or a stock formation. Drag players (they snap to the grid), "
                         "click one to move / swap him or change his position (WR, TE, RB, FB). Green = NFL-legal.")
        root = QHBoxLayout(self)
        left = QVBoxLayout()
        root.addLayout(left, 2)
        left.addWidget(QLabel("<b>Modern templates</b>"))
        self.templates = QListWidget()
        self.templates.setStyleSheet(BIG)
        for name, (blurb, _players) in lib.FORMATION_TEMPLATES.items():
            item = QListWidgetItem(name)
            item.setToolTip(blurb)
            self.templates.addItem(item)
        self.templates.itemClicked.connect(lambda item: self._use_template(item.text()))
        left.addWidget(self.templates, 2)
        left.addWidget(QLabel("<b>…or start from a stock formation</b>"))
        self.stock = QComboBox()
        self.stock.setStyleSheet(BIG)
        self.stock.activated.connect(self._use_stock)
        left.addWidget(self.stock)
        self.blurb = QLabel("")
        self.blurb.setWordWrap(True)
        left.addWidget(self.blurb)
        self.scene = FieldScene(True)
        self.view = FieldView(self.scene)
        root.addWidget(self.view, 4)
        right = QVBoxLayout()
        root.addLayout(right, 2)
        form = QFormLayout()
        self.name_edit = QLineEdit()
        self.name_edit.setMaxLength(40)
        self.name_edit.setStyleSheet(BIG)
        self.name_edit.setPlaceholderText("Formation name (e.g. Gun Trips Rt)")
        form.addRow("Name", self.name_edit)
        self.personnel = QLabel("—")
        self.personnel.setWordWrap(True)
        form.addRow("Personnel", self.personnel)
        right.addLayout(form)
        box = QGroupBox("Selected player")
        bl = QFormLayout(box)
        self.sel_label = QLabel("click a player on the field")
        bl.addRow("Who", self.sel_label)
        self.pos_combo = QComboBox()
        self.pos_combo.setStyleSheet(BIG)
        for label, kind in lib.SKILL_CHOICES:
            self.pos_combo.addItem(label, kind)
        self.pos_combo.setToolTip("Change who plays this spot: a second RB instead of the FB, a WR instead of the TE…")
        self.pos_combo.activated.connect(self._position_changed)
        self.pos_combo.setEnabled(False)
        bl.addRow("Position", self.pos_combo)
        self.x_spin = QDoubleSpinBox(); self.x_spin.setRange(-26, 26); self.x_spin.setSingleStep(0.5); self.x_spin.setSuffix(" yd")
        self.z_spin = QDoubleSpinBox(); self.z_spin.setRange(-15, 1); self.z_spin.setSingleStep(0.5); self.z_spin.setSuffix(" yd")
        self.x_spin.valueChanged.connect(self._spin_changed)
        self.z_spin.valueChanged.connect(self._spin_changed)
        bl.addRow("Left / right", self.x_spin)
        bl.addRow("Depth (− = backfield)", self.z_spin)
        self.swap_combo = QComboBox()
        self.swap_button = QPushButton("Swap spots with…")
        self.swap_button.clicked.connect(self._swap)
        row = QHBoxLayout(); row.addWidget(self.swap_combo, 1); row.addWidget(self.swap_button)
        bl.addRow("Swap", row)
        right.addWidget(box)
        self.flip = QPushButton("Flip left ↔ right")
        self.flip.clicked.connect(self._flip)
        right.addWidget(self.flip)
        right.addWidget(QLabel("<b>NFL alignment check</b>"))
        self.legal = QListWidget()
        self.legal.setMaximumHeight(140)
        right.addWidget(self.legal)
        self.allow_illegal = QCheckBox("Let me use an illegal alignment anyway")
        right.addWidget(self.allow_illegal)
        right.addStretch(1)
        self.positions: list[list[float]] = []
        self.kinds: list[int] = []
        self.codes: list[int] = []
        self.labels: list[str] = []
        self.category_index = 0
        self.category_positions: list[int] | None = None
        self.note = ""
        self.warnings: list[str] = []
        self.donor_index = 0
        self.selected: int | None = None
        self._updating = False
        self._issues: list[str] = ["nothing laid out yet"]

    def initializePage(self) -> None:
        book, body = self.wiz.book, self.wiz.body
        assert book is not None and body is not None
        self.stock.clear()
        for idx in lib.offense_formations(book, body):
            self.stock.addItem(book.formations[idx].name, idx)
        if not self.positions:
            self._use_template(list(lib.FORMATION_TEMPLATES)[0])
            self.templates.setCurrentRow(0)

    # -- personnel
    def _claimed(self) -> dict[int, list[int]]:
        """Groups already written by the other designs of this session."""
        return {f.category_index: list(f.category_positions) for f in self.wiz.designed
                if f.category_positions is not None and f is not self.wiz.current}

    def _take_plan(self, plan: lib.PersonnelPlan) -> None:
        self.codes = list(plan.codes)
        self.kinds = [c & 0x1F for c in plan.codes]
        self.labels = [codec.position_label(c) for c in plan.codes]
        self.category_index = plan.category_index
        self.category_positions = None if plan.category_positions is None else list(plan.category_positions)
        self.note = plan.note
        self.warnings = list(plan.warnings)
        self.donor_index = lib.donor_for_personnel(self.wiz.book, self.wiz.body, plan)
        self._show_personnel()

    def _show_personnel(self) -> None:
        text = ", ".join(self.labels[6:]) + "   —   " + self.note
        if self.warnings:
            text += "\n⚠ " + " ".join(self.warnings)
        self.personnel.setText(text)

    def _replan(self) -> None:
        """Re-rank the depth-chart codes and find the group that fields this mix."""
        xs = [p[0] for p in self.positions]
        codes = lib.ranked_codes(self.kinds, xs)
        try:
            plan = lib.resolve_personnel(self.wiz.book, self.wiz.body, codes, self._claimed())
        except ValueError as exc:
            QMessageBox.warning(self, "Personnel", str(exc))
            return
        old_selected = self.selected
        self.positions = [self.positions[plan.slot_order[s]] for s in range(11)]
        self._take_plan(plan)
        self._refresh()
        if old_selected is not None:
            self._select(plan.slot_order.index(old_selected))

    def _position_changed(self, combo_index: int) -> None:
        if self.selected is None or self.selected not in lib.SKILL_SLOTS:
            return
        kind = self.pos_combo.itemData(combo_index)
        if kind is None or self.kinds[self.selected] == kind:
            return
        self.kinds[self.selected] = int(kind)
        self._replan()

    # -- sources
    def _use_template(self, name: str) -> None:
        blurb, players = lib.FORMATION_TEMPLATES[name]
        fit = lib.fit_template(self.wiz.book, self.wiz.body, players, self._claimed())
        self.positions = [[float(x), float(z)] for x, z in fit.slot_positions]
        self.codes = list(fit.codes)
        self.kinds = list(fit.slot_kinds)
        self.labels = list(fit.labels)
        self.category_index = fit.category_index
        self.category_positions = None if fit.category_positions is None else list(fit.category_positions)
        self.note = fit.note
        self.warnings = list(fit.warnings)
        self.donor_index = fit.donor_formation_index
        self.name_edit.setText(name[:40])
        self._show_personnel()
        self.blurb.setText(blurb)
        self._refresh()

    def _use_stock(self, combo_index: int) -> None:
        idx = self.stock.itemData(combo_index)
        rec = lib.formation_record(self.wiz.body, idx)
        self.category_index = lib.formation_category(self.wiz.body, idx)
        self.donor_index = idx
        self.codes = list(lib.category_positions(self.wiz.body, self.category_index))
        self.kinds = [c & 0x1F for c in self.codes]
        self.labels = [codec.position_label(c) for c in self.codes]
        self.category_positions = None
        self.note = f"stock group “{self.wiz.book.categories[self.category_index].name}”"
        self.warnings = []
        self.positions = [[float(s.x[0]), float(s.z[0])] for s in rec.slots]
        self.name_edit.setText(f"{self.wiz.book.formations[idx].name} v2"[:40])
        self._show_personnel()
        self.blurb.setText(f"Started from stock “{self.wiz.book.formations[idx].name}”.")
        self._refresh()

    # -- field
    def _refresh(self) -> None:
        self.scene.set_tokens([(x, z) for x, z in self.positions], self.labels, True, self._moved, self._select)
        self.swap_combo.clear()
        for s in range(11):
            self.swap_combo.addItem(f"{self.labels[s]} (slot {s})", s)
        self._legality()
        self.completeChanged.emit()

    def _select(self, slot: int) -> None:
        self.selected = slot
        self.scene.highlight(slot)
        self._updating = True
        self.sel_label.setText(f"{self.labels[slot]}  (slot {slot})")
        self.x_spin.setValue(self.positions[slot][0] / YD)
        self.z_spin.setValue(self.positions[slot][1] / YD)
        skill = slot in lib.SKILL_SLOTS
        self.pos_combo.setEnabled(skill)
        if skill:
            row = next((k for k in range(self.pos_combo.count()) if self.pos_combo.itemData(k) == self.kinds[slot]), 0)
            self.pos_combo.setCurrentIndex(row)
        self._updating = False

    def _moved(self, slot: int) -> None:
        x, z = from_scene(self.scene.tokens[slot].pos())
        self.positions[slot] = [x, z]
        if slot == self.selected:
            self._select(slot)
        self._legality()

    def _spin_changed(self, _v: float) -> None:
        if self._updating or self.selected is None:
            return
        self.positions[self.selected] = [self.x_spin.value() * YD, self.z_spin.value() * YD]
        self.scene.tokens[self.selected].setPos(to_scene(*self.positions[self.selected]))
        self._legality()

    def _swap(self) -> None:
        if self.selected is None:
            return
        other = self.swap_combo.currentData()
        if other is None or other == self.selected:
            return
        self.positions[self.selected], self.positions[other] = self.positions[other], self.positions[self.selected]
        self._refresh()
        self._select(self.selected)

    def _flip(self) -> None:
        for p in self.positions:
            p[0] = -p[0]
        self._refresh()

    def _legality(self) -> None:
        slots = [codec.FormationSlot(0, codec.NO_MIRROR, 3, [int(round(x))] * 3, [int(round(z))] * 3) for x, z in self.positions]
        self._issues = codec.formation_legality(slots, self.codes, True)
        self.legal.clear()
        if not self._issues:
            it = QListWidgetItem("Legal ✔")
            it.setForeground(QBrush(QColor("#2e7d32")))
            self.legal.addItem(it)
        for issue in self._issues:
            it = QListWidgetItem(issue)
            it.setForeground(QBrush(QColor("#c62828")))
            self.legal.addItem(it)
        self.completeChanged.emit()

    def isComplete(self) -> bool:
        return bool(self.positions) and (not self._issues or self.allow_illegal.isChecked())

    def validatePage(self) -> bool:
        name = self.name_edit.text().strip() or "Custom"
        current = DesignedFormation(
            name=name, category_index=self.category_index, donor_formation_index=self.donor_index,
            positions=[(int(round(x)), int(round(z))) for x, z in self.positions],
            kinds=list(self.kinds), labels=list(self.labels),
            codes=list(self.codes), category_positions=None if self.category_positions is None else list(self.category_positions),
            personnel_note=self.note,
        )
        # Re-entering this page for the same design keeps its plays.
        cur = self.wiz.current
        if cur is not None and cur.positions == current.positions and cur.name == name and cur.codes == current.codes:
            return True
        self.wiz.current = current
        self.wiz.designed.append(current)
        return True


# ---------------------------------------------------------------------------
# Step 3 — play type
# ---------------------------------------------------------------------------

class PlayTypePage(QWizardPage):
    def __init__(self, wizard: CreatePlayWizard):
        super().__init__()
        self.wiz = wizard
        self.setTitle("Step 3 — Run or pass?")
        self.setSubTitle("Pick the kind of play. The next step fills in every player's job automatically; you can change any of them.")
        root = QHBoxLayout(self)
        left = QVBoxLayout()
        root.addLayout(left, 1)
        self.radios: dict[str, QRadioButton] = {}
        for key, label, tip in (
            ("pass", "Pass", "drop back and throw"),
            ("pa_pass", "Play-action pass", "fake the handoff, then throw"),
            ("run", "Run", "hand off (dive, zone, power, toss, draw…)"),
            ("sneak", "QB sneak / Tush push", "QB follows the center, backs push"),
            ("keeper", "QB keeper", "QB keeps it around the edge"),
            ("reverse", "Reverse", "handoff to the back, who hands to a receiver going the other way"),
        ):
            rb = QRadioButton(label)
            rb.setStyleSheet(HUGE)
            rb.setToolTip(tip)
            rb.toggled.connect(self._refresh_options)
            self.radios[key] = rb
            left.addWidget(rb)
        self.radios["pass"].setChecked(True)
        left.addStretch(1)
        right = QVBoxLayout()
        root.addLayout(right, 1)
        self.concept_box = QGroupBox("Pass concept")
        cl = QVBoxLayout(self.concept_box)
        self.concepts = QListWidget()
        self.concepts.setStyleSheet(BIG)
        for name, con in lib.PASS_CONCEPTS.items():
            separator = ": " if name in lib.SCREEN_CONCEPTS else " — "
            it = QListWidgetItem(f"{name}{separator}{con['blurb']}")
            it.setData(Qt.UserRole, name)
            self.concepts.addItem(it)
        self.concepts.setCurrentRow(0)
        cl.addWidget(self.concepts)
        right.addWidget(self.concept_box)
        self.run_box = QGroupBox("Run scheme")
        rl = QFormLayout(self.run_box)
        self.schemes = QListWidget()
        self.schemes.setStyleSheet(BIG)
        for name, sch in lib.RUN_SCHEMES.items():
            it = QListWidgetItem(f"{name} — {sch['blurb']}")
            it.setData(Qt.UserRole, name)
            self.schemes.addItem(it)
        self.schemes.setCurrentRow(0)
        rl.addRow(self.schemes)
        self.direction = QComboBox()
        for d in ("left", "middle", "right"):
            self.direction.addItem(d.title(), d)
        self.direction.setCurrentIndex(2)
        rl.addRow("Direction", self.direction)
        self.carrier = QComboBox()
        rl.addRow("Ball carrier", self.carrier)
        self.direct_snap = QCheckBox("Snap straight to the carrier (wildcat)")
        rl.addRow(self.direct_snap)
        self.reverse_to = QComboBox()
        rl.addRow("Reverse to", self.reverse_to)
        right.addWidget(self.run_box)
        self.fake_box = QGroupBox("Play action")
        fl = QFormLayout(self.fake_box)
        self.fake_to = QComboBox()
        fl.addRow("Fake handoff to", self.fake_to)
        right.addWidget(self.fake_box)
        self._make_screen_options(right)
        right.addStretch(1)

    def _make_screen_options(self, layout: QVBoxLayout) -> None:
        self.screen_box = QGroupBox("Screen: EXPERIMENTAL / UNWITNESSED")
        form = QFormLayout(self.screen_box)
        self.screen_receiver = QComboBox()
        form.addRow("Intended receiver", self.screen_receiver)
        self.screen_side = QComboBox()
        self.screen_side.addItem("Left", -1)
        self.screen_side.addItem("Right", 1)
        form.addRow("Release side", self.screen_side)
        self.screen_level = QComboBox()
        for label, level in (("Retail timing", "Retail"), ("A: Longer line hold", "A"),
                             ("B: Shallower QB drop", "B"), ("C: Explicit pass delay", "C"),
                             ("D: Combine A, B and C", "D")):
            self.screen_level.addItem(label, level)
        self.screen_level.setCurrentIndex(4)
        form.addRow("Timing starting point", self.screen_level)
        self.screen_hold = QDoubleSpinBox()
        self.screen_hold.setRange(0.1, 6.3); self.screen_hold.setSingleStep(0.1)
        self.screen_hold.setDecimals(1); self.screen_hold.setSuffix(" seconds")
        form.addRow("Line hold before release", self.screen_hold)
        self.screen_drop = QDoubleSpinBox()
        self.screen_drop.setRange(0, 20); self.screen_drop.setSingleStep(1)
        self.screen_drop.setSuffix(" yards")
        form.addRow("Nominal QB drop", self.screen_drop)
        self.screen_delay = QDoubleSpinBox()
        self.screen_delay.setRange(0, 6.3); self.screen_delay.setSingleStep(0.1)
        self.screen_delay.setDecimals(1); self.screen_delay.setSuffix(" seconds")
        self.screen_delay.setSpecialValueText("Retail default timer")
        form.addRow("Pass delay", self.screen_delay)
        note = QLabel("Three linemen hold, release, then block. Two keep protecting. "
                      "A zero pass delay uses the retail timer; it does not mean an immediate throw. "
                      "The QB looks at the chosen slot first, but may choose another receiver. "
                      "WR and TE screens adapt the HB sequence and need separate play tests.")
        note.setWordWrap(True)
        form.addRow(note)
        layout.addWidget(self.screen_box)
        self.screen_level.currentIndexChanged.connect(self._screen_timing)
        self.concepts.currentItemChanged.connect(self._screen_options)
        self.screen_receiver.currentIndexChanged.connect(lambda _i: self.completeChanged.emit())
        self._screen_timing()
        self.screen_box.hide()

    def _screen_timing(self, *_args: object) -> None:
        settings = lib.screen_preset("HB", level=self.screen_level.currentData())
        self.screen_hold.setValue(settings.hold_seconds)
        self.screen_drop.setValue(settings.drop_yards)
        self.screen_delay.setValue(settings.pass_delay)

    def _screen_options(self, *_args: object) -> None:
        if not hasattr(self, "screen_box"):
            return
        item = self.concepts.currentItem()
        concept = item.data(Qt.UserRole) if item else None
        active = concept in lib.SCREEN_CONCEPTS and self.play_type() in ("pass", "pa_pass")
        self.screen_box.setVisible(active)
        previous = self.screen_receiver.currentData()
        self.screen_receiver.blockSignals(True)
        self.screen_receiver.clear()
        cur = self.wiz.current
        if active and cur is not None:
            kind = {"HB": lib.HB, "WR": lib.WR, "TE": lib.TE}[lib.SCREEN_CONCEPTS[concept]]
            for slot in range(6, 11):
                if cur.kinds[slot] == kind:
                    self.screen_receiver.addItem(f"{cur.labels[slot]} (assignment slot {slot})", slot)
            index = self.screen_receiver.findData(previous)
            if index >= 0:
                self.screen_receiver.setCurrentIndex(index)
        self.screen_receiver.blockSignals(False)
        self.screen_box.setToolTip("Choose Pass and a formation containing the receiver's position.")
        self.completeChanged.emit()

    def isComplete(self) -> bool:
        item = self.concepts.currentItem()
        if (item and item.data(Qt.UserRole) in lib.SCREEN_CONCEPTS
                and self.play_type() in ("pass", "pa_pass")):
            return self.play_type() == "pass" and self.screen_receiver.currentData() is not None
        return super().isComplete()

    def initializePage(self) -> None:
        cur = self.wiz.current
        assert cur is not None
        for combo in (self.carrier, self.reverse_to, self.fake_to):
            combo.clear()
        for s in range(11):
            if cur.kinds[s] in (lib.HB, lib.FB, lib.WR, lib.TE):
                self.carrier.addItem(f"{cur.labels[s]} (slot {s})", s)
            if cur.kinds[s] in (lib.HB, lib.FB):
                self.fake_to.addItem(f"{cur.labels[s]} (slot {s})", s)
            if cur.kinds[s] in (lib.WR, lib.TE):
                self.reverse_to.addItem(f"{cur.labels[s]} (slot {s})", s)
        self._refresh_options()

    def play_type(self) -> str:
        return next(k for k, rb in self.radios.items() if rb.isChecked())

    def _refresh_options(self, *_a: object) -> None:
        if not hasattr(self, "fake_box"):
            return
        t = self.play_type()
        self.concept_box.setVisible(t in ("pass", "pa_pass"))
        self.run_box.setVisible(t in ("run", "keeper", "sneak", "reverse"))
        self.fake_box.setVisible(t == "pa_pass")
        self.schemes.setVisible(t == "run")
        self.reverse_to.setVisible(t == "reverse")
        self.carrier.setVisible(t in ("run", "reverse"))
        self.direct_snap.setVisible(t == "run")
        self._screen_options()

    def build_spec(self) -> tuple[lib.PlaySpec, str]:
        cur = self.wiz.current
        assert cur is not None
        t = self.play_type()
        concept = self.concepts.currentItem().data(Qt.UserRole) if self.concepts.currentItem() else "4 Verts"
        scheme = self.schemes.currentItem().data(Qt.UserRole) if self.schemes.currentItem() else "Inside Zone"
        sch = lib.RUN_SCHEMES.get(scheme, {})
        spec = lib.PlaySpec(
            name="", play_type=t, positions=list(cur.positions), kinds=list(cur.kinds), assignments={},
            carrier_slot=self.carrier.currentData() if t in ("run", "reverse") else self.fake_to.currentData(),
            handoff_kind=(sch.get("kind") or 0) if t == "run" else 0,
            run_direction=self.direction.currentData() or "right",
            reverse_slot=self.reverse_to.currentData() if t == "reverse" else None,
            direct_snap=self.direct_snap.isChecked() if t == "run" else False,
        )
        if concept in lib.SCREEN_CONCEPTS and t in ("pass", "pa_pass"):
            spec.screen = lib.ScreenPreset(
                lib.SCREEN_CONCEPTS[concept], self.screen_receiver.currentData(),
                self.screen_side.currentData(), self.screen_hold.value(),
                self.screen_drop.value(), self.screen_delay.value(),
            )
        lib.default_assignments(spec, concept=concept, scheme=scheme if t == "run" else None)
        if t == "pa_pass" and spec.carrier_slot is not None:
            spec.assignments[spec.carrier_slot] = lib.PlayerAssignment("fake_carry")
        label = concept if t in ("pass", "pa_pass") else (scheme if t == "run" else t)
        return spec, label


# ---------------------------------------------------------------------------
# Step 4 — assignments
# ---------------------------------------------------------------------------

RUN_TYPES = ("run", "sneak", "keeper", "reverse")


class DrawScene(FieldScene):
    """A field where dragging from a player draws his route (or the carrier's path);
    a plain click opens his job menu."""

    def __init__(self, on_click: Callable[[int], None], on_drawn: Callable[[int, list], None],
                 can_draw: Callable[[int], bool]):
        super().__init__(True)
        self.on_click = on_click
        self.on_drawn = on_drawn
        self.can_draw = can_draw
        self._slot: int | None = None
        self._pts: list[tuple[float, float]] = []
        self._path = None

    def token_at(self, pos: QPointF):
        for tok in self.tokens.values():
            if (tok.pos() - pos).manhattanLength() <= PlayerToken.RADIUS * 1.8:
                return tok
        return None

    def mousePressEvent(self, event):
        tok = self.token_at(event.scenePos()) if event.button() == Qt.LeftButton else None
        if tok is None:
            super().mousePressEvent(event)
            return
        self._slot = tok.slot
        self._pts = [from_scene(tok.pos())]
        event.accept()

    def mouseMoveEvent(self, event):
        if self._slot is None:
            super().mouseMoveEvent(event)
            return
        if not self.can_draw(self._slot):
            return
        self._pts.append(from_scene(event.scenePos()))
        path = QPainterPath(to_scene(*self._pts[0]))
        for x, z in self._pts[1:]:
            path.lineTo(to_scene(x, z))
        if self._path is None:
            pen = QPen(QColor("#ff8a65"), 2.5, Qt.DashLine)
            pen.setCosmetic(True)
            self._path = self.addPath(path, pen)
            self._path.setZValue(5)
        else:
            self._path.setPath(path)

    def mouseReleaseEvent(self, event):
        if self._slot is None:
            super().mouseReleaseEvent(event)
            return
        slot, pts = self._slot, self._pts
        self._slot, self._pts = None, []
        if self._path is not None:
            self.removeItem(self._path)
            self._path = None
        length = sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts, pts[1:]))
        if length < 1.5 * YD or not self.can_draw(slot):
            self.on_click(slot)
        else:
            self.on_drawn(slot, pts)
        event.accept()

    def finish_drawing(self, slot: int, points_cm: list[tuple[float, float]]) -> None:
        """Programmatic equivalent of a drag (tests / scripts)."""
        self.on_drawn(slot, list(points_cm))


class AssignPage(QWizardPage):
    def __init__(self, wizard: CreatePlayWizard):
        super().__init__()
        self.wiz = wizard
        self.setTitle("Step 4 — Give everyone a job")
        self.setSubTitle("Drag from a player to DRAW his route (or the ball carrier's path). Click him for a menu of "
                         "routes, blocks, carries, lead blocks and fakes. The play is checked against the game's rules as you go.")
        root = QHBoxLayout(self)
        self.scene = DrawScene(self._menu_for, self._drawn, self._can_draw)
        self.view = FieldView(self.scene)
        root.addWidget(self.view, 4)
        side = QVBoxLayout()
        root.addLayout(side, 2)
        form = QFormLayout()
        self.name_edit = QLineEdit()
        self.name_edit.setMaxLength(40)
        self.name_edit.setStyleSheet(BIG)
        form.addRow("Play name", self.name_edit)
        side.addLayout(form)
        side.addWidget(QLabel("<b>Jobs</b> (click a player on the field or in this list to change)"))
        self.jobs = QListWidget()
        self.jobs.setStyleSheet(BIG)
        self.jobs.itemClicked.connect(lambda item: self._menu_for(item.data(Qt.UserRole)))
        side.addWidget(self.jobs, 1)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        side.addWidget(self.status)
        self.add_button = QPushButton("Add this play and design another in this formation")
        self.add_button.setStyleSheet(BIG)
        self.add_button.clicked.connect(self._add_and_continue)
        side.addWidget(self.add_button)
        hint = QLabel("✏ Drawing: press on a receiver, drag the route, let go. The game runs up to three moves "
                      "(stems, 30/45/60° breaks in, 45° out, ins/outs, comebacks) — what it will run shows in white.\n"
                      "Next ➜ adds this play and goes to Finalize. Use “Back” twice to lay out another formation.")
        hint.setWordWrap(True)
        side.addWidget(hint)
        self.spec: lib.PlaySpec | None = None
        self.label = ""
        self.scheme: str | None = None
        self.concept: str | None = None
        self._error: str | None = None
        self._raw: dict[int, list[tuple[float, float]]] = {}

    def initializePage(self) -> None:
        self.spec, self.label = self.wiz.page_type.build_spec()
        self.scheme = self.label if self.spec.play_type == "run" else None
        self.concept = self.label if self.spec.play_type in ("pass", "pa_pass") else None
        self._raw = {}
        cur = self.wiz.current
        n = len(cur.plays) + 1
        self.name_edit.setText(f"{self.label} {n}"[:40] if self.spec.play_type != "run" else f"{self.spec.run_direction.title()} {self.label}"[:40])
        self.scene.set_tokens([(float(x), float(z)) for x, z in cur.positions], cur.labels, False, lambda _s: None, lambda _s: None)
        self._refresh()

    def _chains(self) -> list[lib.Chain]:
        return lib.build_chains(self.spec, self.scheme)

    def _refresh(self) -> None:
        cur = self.wiz.current
        chains = self._chains()
        self.scene.clear_art()
        faint = QColor(255, 138, 101, 110)
        for s, pts in self._raw.items():
            segs = [codec.ArtSegment([(x, z) for x, z in pts], style="dashed")]
            self.scene.draw_art(segs, faint)
        for s in range(11):
            x0, z0 = cur.positions[s]
            nodes = [codec.Node(op, 0, list(vals)) for op, vals in chains[s]]
            segs = codec.play_art(nodes, (float(x0), float(z0)), side=1 if x0 >= 0 else -1, wide_left=x0 < 0)
            if self.spec.screen and self.spec.assignments[s].kind == "screen_receiver":
                # Show the proved behind-line endpoint band; lateral movement needs gameplay.
                _x, endpoint_z = lib.screen_endpoint(x0, x0)
                segs = [codec.ArtSegment([(-1798.32, endpoint_z), (1798.32, endpoint_z)], style="dashed"),
                        codec.ArtSegment([(x0, z0), (x0, endpoint_z)], style="dashed", end_marker="arrow")]
            self.scene.draw_art(segs, QColor("#ffd54f") if s == self.spec.carrier_slot else QColor("#ffffff"))
        self.jobs.clear()
        for s in range(11):
            it = QListWidgetItem(f"{cur.labels[s]}: {self._describe(s)}")
            it.setData(Qt.UserRole, s)
            self.jobs.addItem(it)
        donor, flags = self.wiz.reference_play(self.spec.play_type, self.scheme)
        _donor_flags, donor_chains = lib.play_chains(self.wiz.body, donor)
        self._error = lib.validate_chains(flags, donor_chains, chains)
        screen_note = ""
        if self.spec.screen:
            from mod_editor.core.nfl2k5_formation_play_writer import NODE_CAPACITY, authored_node_cost
            cost = authored_node_cost(chains)
            staged = sum(authored_node_cost(p.chains) for f in self.wiz.designed for p in f.plays)
            remaining = NODE_CAPACITY - self.wiz.book.node_count - staged
            if cost > remaining:
                self._error = f"This screen needs {cost} nodes, with {remaining} remaining in this design."
            screen_note = (f"EXPERIMENTAL / UNWITNESSED. {cost} nodes ({cost * 8} bytes); "
                           f"{remaining} available before this play. Receiver: assignment slot "
                           f"{self.spec.screen.receiver_slot}. Dashed guide: endpoint 1.5 yards behind "
                           "the line, bounded laterally to 19 2/3 yards unless already outside. "
                           "The guide does not predict lateral travel, arrival time or a catch.")
        if self._error:
            self.status.setText("✖ " + self._error)
            self.status.setStyleSheet("color:#c62828;" + BIG)
        else:
            self.status.setText("The play passes the data checks. " + screen_note if self.spec.screen
                                else "✔ The game accepts this play.")
            self.status.setStyleSheet("color:#2e7d32;" + BIG)
        self.completeChanged.emit()

    def _describe(self, s: int) -> str:
        a = self.spec.assignments.get(s)
        kinds = self.spec.kinds
        if self.spec.screen and a is not None:
            if a.kind == "screen_release":
                return f"hold {self.spec.screen.hold_seconds:g} seconds, release, then block"
            if a.kind == "screen_receiver":
                return f"intended screen receiver (assignment slot {s}); endpoint behind the line"
            if a.kind == "qb":
                return f"drop, look at assignment slot {self.spec.screen.receiver_slot}, then pass"
        if a is not None and a.kind == "custom":
            return f"✏ drawn — {a.route}"
        if kinds[s] == lib.QB and not self.spec.direct_snap:
            return {"pass": "drop back and throw", "pa_pass": "fake, then throw", "sneak": "sneak", "keeper": "keep it", "reverse": "hand off"}.get(self.spec.play_type, "hand off")
        if a is None:
            return "block"
        if a.kind == "route":
            return f"route: {a.route}" + (f" ({a.depth:.0f} yd)" if a.depth else "")
        if a.kind == "carry":
            return "BALL CARRIER"
        if a.kind == "fake_carry":
            return "fake handoff, then block"
        if a.kind == "lead":
            return "lead block"
        if a.kind == "stalk":
            return "release and block downfield"
        if a.kind == "block":
            return {"pass": "pass block", "straight": "run block ahead", "left": "run block left", "right": "run block right",
                    "pull-left": "pull left", "pull-right": "pull right"}.get(a.block_style, a.block_style)
        return a.kind

    # -- drawing
    def _can_draw(self, slot: int) -> bool:
        if self.spec is None:
            return False
        kind = self.spec.kinds[slot]
        if kind in (lib.WR, lib.TE, lib.HB, lib.FB):
            return True
        if kind == lib.QB:
            return self.spec.direct_snap or self.spec.play_type in ("keeper", "sneak")
        return False

    def _drawn(self, slot: int, pts: list) -> None:
        cur = self.wiz.current
        x0 = cur.positions[slot][0]
        side = 1 if x0 >= 0 else -1
        kind = self.spec.kinds[slot]
        run = self.spec.play_type in RUN_TYPES
        try:
            if kind == lib.QB and self.spec.play_type in ("keeper", "sneak") and not self.spec.direct_snap:
                qb_slot = slot
                shotgun = self.spec.positions[qb_slot][1] <= codec.SHOTGUN_DEPTH_THRESHOLD_CM
                _lane, path, desc = lib.drawn_run_path(pts, side)
                chain = [lib.start(4), (0x03, [0]), (0x04, [0, 0.0, (-1.0 if shotgun else -3.0) * YD, 0]),
                         (0x15, [0, path[1] * YD, path[2] * YD, 2, 15, 0, 0])]
                desc = "QB " + desc
            elif run and slot == self.spec.carrier_slot and self.spec.direct_snap:
                _lane, path, desc = lib.drawn_run_path(pts, side)
                chain = [lib.start(4), (0x03, [0]), (0x15, [0, path[1] * YD, path[2] * YD, 2, 15, 0, 0])]
                desc = "takes the snap, " + desc
            elif run and slot == self.spec.carrier_slot and self.spec.play_type in ("run", "reverse"):
                lane, path, desc = lib.drawn_run_path(pts, side)
                chain = lib.carrier_chain(lane, path)
                desc = "BALL CARRIER, " + desc
            else:
                chain, desc = lib.quantize_drawn_route(pts, side)
        except ValueError as exc:
            self.status.setText("✖ " + str(exc))
            self.status.setStyleSheet("color:#c62828;" + BIG)
            return
        self.spec.assignments[slot] = lib.PlayerAssignment("custom", route=desc, custom=chain)
        self._raw[slot] = [(float(x), float(z)) for x, z in pts]
        self._refresh()

    def _default_for(self, slot: int) -> lib.PlayerAssignment:
        probe = lib.PlaySpec(name="", play_type=self.spec.play_type, positions=list(self.spec.positions),
                             kinds=list(self.spec.kinds), assignments={}, carrier_slot=self.spec.carrier_slot,
                             handoff_kind=self.spec.handoff_kind, run_direction=self.spec.run_direction,
                             reverse_slot=self.spec.reverse_slot, direct_snap=self.spec.direct_snap)
        if self.spec.screen:
            from dataclasses import replace
            probe.screen = replace(self.spec.screen)
        lib.default_assignments(probe, concept=self.concept, scheme=self.scheme)
        return probe.assignments.get(slot) or lib.PlayerAssignment("block", block_style="pass")

    def _clear_drawn(self, slot: int) -> None:
        self._raw.pop(slot, None)
        self.spec.assignments[slot] = self._default_for(slot)
        self._refresh()

    # -- menu
    def _menu_for(self, slot: int) -> None:
        cur = self.wiz.current
        kind = self.spec.kinds[slot]
        menu = QMenu(self)
        menu.setStyleSheet(BIG)
        menu.addSection(f"{cur.labels[slot]} — what does he do?")
        run = self.spec.play_type in RUN_TYPES
        a = self.spec.assignments.get(slot)
        if a is not None and a.kind == "custom":
            act = menu.addAction("Clear the drawn route (back to the default job)")
            act.triggered.connect(lambda: self._clear_drawn(slot))
        if self._can_draw(slot):
            menu.addAction("✏ Tip: drag from him on the field to draw his route").setEnabled(False)
        if kind in (lib.WR, lib.TE, lib.HB, lib.FB) or (kind == lib.QB and self.spec.direct_snap):
            routes = menu.addMenu("Run a route")
            for r in lib.ROUTE_LIBRARY:
                act = routes.addAction(f"{r.name} — {r.blurb}")
                act.triggered.connect(lambda _c=False, name=r.name: self._set(slot, lib.PlayerAssignment("route", route=name)))
            depth = menu.addAction("Set route depth…")
            depth.triggered.connect(lambda: self._depth(slot))
            if run and self.spec.play_type in ("run", "reverse"):
                act = menu.addAction("Carry the ball")
                act.triggered.connect(lambda: self._carrier(slot))
            if kind in (lib.HB, lib.FB):
                act = menu.addAction("Lead block")
                act.triggered.connect(lambda: self._set(slot, lib.PlayerAssignment("lead")))
                if self.spec.play_type == "pa_pass":
                    act = menu.addAction("Fake handoff to him, then block")
                    act.triggered.connect(lambda: self._fake(slot))
            act = menu.addAction("Release and block downfield")
            act.triggered.connect(lambda: self._set(slot, lib.PlayerAssignment("stalk")))
            act = menu.addAction("Stay in and pass block")
            act.triggered.connect(lambda: self._set(slot, lib.PlayerAssignment("block", block_style="pass")))
        elif kind in lib.OL_KINDS:
            for label, style in (("Block straight ahead", "straight"), ("Block to the left", "left"), ("Block to the right", "right"),
                                 ("Pull left", "pull-left"), ("Pull right", "pull-right"), ("Pass set", "pass")):
                act = menu.addAction(label)
                act.triggered.connect(lambda _c=False, st=style: self._set(slot, lib.PlayerAssignment("block", block_style=st)))
        else:
            menu.addAction("The quarterback's job comes from the play type (step 3)" +
                           (" — or draw his path on the field." if self._can_draw(slot) else ".")).setEnabled(False)
        menu.exec_(QCursor.pos())

    def _set(self, slot: int, a: lib.PlayerAssignment) -> None:
        if slot == self.spec.carrier_slot and a.kind not in ("carry",):
            self.spec.carrier_slot = None if self.spec.play_type != "run" else self.spec.carrier_slot
        self._raw.pop(slot, None)
        self.spec.assignments[slot] = a
        self._refresh()

    def _depth(self, slot: int) -> None:
        a = self.spec.assignments.get(slot)
        if a is None or a.kind != "route":
            QMessageBox.information(self, "Route depth", "Give him a route first.")
            return
        value, ok = QInputDialog.getDouble(self, "Route depth", f"How many yards before {a.route} breaks / ends?", a.depth or lib.ROUTES_BY_NAME[a.route].default_depth, 1, 40, 0)
        if ok:
            a.depth = value
            self._refresh()

    def _carrier(self, slot: int) -> None:
        old = self.spec.carrier_slot
        self.spec.carrier_slot = slot
        if old is not None and old != slot:
            self._raw.pop(old, None)
            self.spec.assignments[old] = lib.PlayerAssignment("stalk" if self.spec.kinds[old] in (lib.WR, lib.TE) else "lead")
        self._raw.pop(slot, None)
        self.spec.assignments[slot] = lib.PlayerAssignment("carry")
        self._refresh()

    def _fake(self, slot: int) -> None:
        old = self.spec.carrier_slot
        self.spec.carrier_slot = slot
        if old is not None and old != slot:
            self.spec.assignments[old] = lib.PlayerAssignment("block", block_style="pass")
        self._raw.pop(slot, None)
        self.spec.assignments[slot] = lib.PlayerAssignment("fake_carry")
        self._refresh()

    def isComplete(self) -> bool:
        return self.spec is not None and self._error is None

    def _commit(self) -> None:
        cur = self.wiz.current
        donor, flags = self.wiz.reference_play(self.spec.play_type, self.scheme)
        cur.plays.append(DesignedPlay(
            name=self.name_edit.text().strip() or self.label, play_type=self.spec.play_type,
            concept_or_scheme=self.label, chains=self._chains(), donor_play_index=donor, play_flags=flags,
        ))

    def _add_and_continue(self) -> None:
        if self._error:
            QMessageBox.warning(self, "Create a Play", self._error)
            return
        self._commit()
        QMessageBox.information(self, "Play added", f"“{self.name_edit.text()}” is in the list. Pick the next play type.")
        self.wiz.back()

    def validatePage(self) -> bool:
        if self._error:
            return False
        self._commit()
        return True


# ---------------------------------------------------------------------------
# Step 5 — finalize
# ---------------------------------------------------------------------------

class FinalizePage(QWizardPage):
    def __init__(self, wizard: CreatePlayWizard):
        super().__init__()
        self.wiz = wizard
        self.setTitle("Step 5 — Put it in the playbook")
        self.setSubTitle("Each design either replaces an outdated stock entry (suggested for you) or is added as new. "
                         "Then Build makes a fresh disc and Launch starts xemu with it.")
        layout = QVBoxLayout(self)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["What", "Name", "Put it where?", "Why that suggestion", "QB read order", "Audible slot"]
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setStyleSheet(BIG)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        layout.addWidget(self.table, 1)
        row = QHBoxLayout()
        self.apply = QPushButton("Add to project")
        self.apply.setStyleSheet(HUGE)
        self.apply.clicked.connect(self._apply)
        self.build = QPushButton("Make disc from project…")
        self.build.setStyleSheet(HUGE)
        self.build.setEnabled(False)
        self.build.clicked.connect(self._build)
        self.launch = QPushButton("Play this disc in xemu")
        self.launch.setStyleSheet(HUGE)
        self.launch.setEnabled(False)
        self.launch.clicked.connect(self._launch)
        row.addWidget(self.apply); row.addWidget(self.build); row.addWidget(self.launch)
        layout.addLayout(row)
        self.hint = QLabel(
            "QB read order: experimental values; receiver-number mapping is not confirmed in-game. "
            "Audible slot: choose a group, or keep Inherit from the formation."
        )
        self.hint.setWordWrap(True)
        layout.addWidget(self.hint)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.status.setStyleSheet(BIG)
        layout.addWidget(self.status)
        self._choices: list[tuple[object, QComboBox]] = []
        self._read_orders: dict[int, tuple[object, list[QSpinBox], int]] = {}
        self._groups: dict[int, tuple[object, QComboBox]] = {}

    def initializePage(self) -> None:
        book, body = self.wiz.book, self.wiz.body
        self.table.setRowCount(0)
        self._choices = []
        self._read_orders = {}
        self._groups = {}
        used_f: set[int] = set()
        used_p: set[int] = set()
        try:
            staged_f, staged_p = self.wiz.host.staged_replace_targets(book.asset_id)
            used_f |= set(staged_f)
            used_p |= set(staged_p)
        except Exception:  # noqa: BLE001 - hosts without staging still get suggestions
            pass
        for f in self.wiz.designed:
            r = self.table.rowCount(); self.table.insertRow(r)
            self.table.setItem(r, 0, QTableWidgetItem("Formation"))
            self.table.setItem(r, 1, QTableWidgetItem(f.name + (f"   ({f.personnel_note})" if f.personnel_note else "")))
            combo = QComboBox()
            suggestions = [(i, why) for i, why in lib.suggest_formations_to_replace(book, body, f.category_index) if i not in used_f]
            for i, why in suggestions[:8]:
                combo.addItem(f"Replace “{book.formations[i].name}”", ("formation", i, why))
            combo.addItem("Add as a new formation", ("formation", None, "keeps every stock formation"))
            if f.replace_index is not None:
                combo.setCurrentIndex(max(0, next((k for k in range(combo.count()) if combo.itemData(k)[1] == f.replace_index), 0)))
            combo.currentIndexChanged.connect(lambda _i, c=combo, r=r: self.table.setItem(r, 3, QTableWidgetItem(c.currentData()[2])))
            self.table.setCellWidget(r, 2, combo)
            self.table.setItem(r, 3, QTableWidgetItem(combo.currentData()[2]))
            if suggestions:
                used_f.add(suggestions[0][0])
            self._choices.append((f, combo))
            for p in f.plays:
                r = self.table.rowCount(); self.table.insertRow(r)
                self.table.setItem(r, 0, QTableWidgetItem("    Play"))
                self.table.setItem(r, 1, QTableWidgetItem(p.name))
                pc = QComboBox()
                # plays are suggested from the donor formation's menu (the plays the new formation inherits)
                psugg = [(i, why) for i, why in lib.suggest_plays_to_replace(book, f.donor_formation_index) if i not in used_p]
                for i, why in psugg[:8]:
                    pc.addItem(f"Replace “{book.plays[i].name}”", ("play", i, why))
                pc.addItem("Add as a new play", ("play", None, "keeps every stock play"))
                pc.currentIndexChanged.connect(lambda _i, c=pc, r=r: self.table.setItem(r, 3, QTableWidgetItem(c.currentData()[2])))
                self.table.setCellWidget(r, 2, pc)
                self.table.setItem(r, 3, QTableWidgetItem(pc.currentData()[2]))
                if psugg:
                    used_p.add(psugg[0][0])
                self._choices.append((p, pc))
                self._add_read_order(r, p, f)
                self._add_audible_group(r, p)
        self.table.resizeColumnsToContents()
        self.status.setText(f"{len(self.wiz.designed)} formation(s), {sum(len(f.plays) for f in self.wiz.designed)} play(s) designed. "
                            "Replacing keeps the playbook the same size; adding grows it (50 formations / 270 plays max).")

    def _add_read_order(self, row: int, play: "DesignedPlay", formation: "DesignedFormation") -> None:
        """Four 1-5 spin boxes over the QB's Dropback node (pass plays only)."""

        qb_slot = next((s for s in range(11) if formation.kinds[s] == lib.QB), 0)
        order = read_order_of(play.chains[qb_slot]) if qb_slot < len(play.chains) else None
        if order is None:
            item = QTableWidgetItem("— (no dropback)")
            item.setFlags(Qt.ItemIsEnabled)
            self.table.setItem(row, 4, item)
            return
        holder = QWidget()
        box = QHBoxLayout(holder)
        box.setContentsMargins(0, 0, 0, 0)
        spins: list[QSpinBox] = []
        for value in order:
            spin = QSpinBox()
            screen = play.concept_or_scheme in lib.SCREEN_CONCEPTS
            spin.setRange(0 if screen else READ_ORDER_MIN, READ_ORDER_MAX)
            spin.setValue(int(value))
            spin.setToolTip(
                "One of the Dropback node's four ordered 1-5 values — the quarterback's read "
                "order. Retail sets them on every dropback; what each number selects is read "
                "from the corpus, not witnessed in game."
            )
            if screen:
                spin.setToolTip("1 to 5 select assignment slots 6 to 10. First zero defaults to slot 7; "
                                "later zeros skip reads. The final target is not forced. UNWITNESSED in play.")
            box.addWidget(spin)
            spins.append(spin)
        self.table.setCellWidget(row, 4, holder)
        self._read_orders[row] = (play, spins, qb_slot)

    def _add_audible_group(self, row: int, play: "DesignedPlay") -> None:
        combo = QComboBox()
        for label, value in AUDIBLE_GROUPS:
            combo.addItem(label, value)
        combo.setToolTip(
            "Which of the formation's three audible slots lists this play. Every populated "
            "retail formation carries exactly one link in each of groups 0, 1 and 2."
        )
        self.table.setCellWidget(row, 5, combo)
        self._groups[row] = (play, combo)

    def _apply(self) -> None:
        book = self.wiz.book
        host = self.wiz.host
        staged = 0
        for play, spins, qb_slot in self._read_orders.values():
            play.chains[qb_slot] = with_read_order(
                play.chains[qb_slot], [spin.value() for spin in spins],
                allow_zero=play.concept_or_scheme in lib.SCREEN_CONCEPTS,
            )
        groups = {id(play): combo.currentData() for play, combo in self._groups.values()}
        try:
            current_formation: DesignedFormation | None = None
            for obj, combo in self._choices:
                kind, target, _why = combo.currentData()
                if isinstance(obj, DesignedFormation):
                    obj.replace_index = target
                    host.create_formation(book.asset_id, obj.donor_formation_index, obj.name, _quiet,
                                          slot_positions=[list(p) for p in obj.positions], category_index=obj.category_index,
                                          replace_index=target, category_positions=obj.category_positions)
                    obj.selector = host.stage_formation_selector(book.asset_id, obj.donor_formation_index, obj.name,
                                                                 [list(p) for p in obj.positions], obj.category_index, target,
                                                                 obj.category_positions)
                    current_formation = obj
                    staged += 1
                else:
                    assert current_formation is not None
                    obj.replace_index = target
                    assignments = [[[op, list(vals)] for op, vals in chain] for chain in obj.chains]
                    link_index = None
                    link_selector = None
                    if target is None or not any(l.play_index == target for l in book.formations[current_formation.replace_index].play_links) if current_formation.replace_index is not None else True:
                        if current_formation.replace_index is not None:
                            link_index = current_formation.replace_index
                        else:
                            link_selector = current_formation.selector
                    host.create_authored_play(book.asset_id, obj.donor_play_index, obj.name, assignments,
                                              link_index, link_selector, _quiet, replace_index=target,
                                              play_flags=obj.play_flags,
                                              link_group=groups.get(id(obj)))
                    staged += 1
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Create a Play", f"Could not stage everything:\n\n{exc}")
            return
        self.status.setText(f"✔ Staged {staged} item(s). Now Build the disc (about two minutes), then Launch.")
        self.build.setEnabled(True)
        self.apply.setEnabled(False)

    def _build(self) -> None:
        preferred = Path.home() / "2K5 Mod Studio Builds"
        preferred.mkdir(exist_ok=True)
        filename, _ = QFileDialog.getSaveFileName(self, "Build the modded disc", str(preferred / "NFL 2K5 Create-a-Play.xiso.iso"), "Xbox XISO (*.iso)")
        if not filename:
            return
        dest = Path(filename)
        if dest.suffix.lower() != ".iso":
            dest = dest.with_suffix(".iso")
        self.status.setText("Building… this copies the whole disc and verifies it (about two minutes).")
        self.build.setEnabled(False)
        from PyQt5.QtWidgets import QApplication
        QApplication.processEvents()
        try:
            result = self.wiz.host.build_iso(dest, lambda stage, done, total: (self.status.setText(f"{stage} ({done}/{total})"), QApplication.processEvents()))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Build failed", str(exc))
            self.build.setEnabled(True)
            return
        self.status.setText(f"✔ Built and verified: {getattr(result, 'output_xiso', dest)}")
        self.launch.setEnabled(True)

    def _launch(self) -> None:
        try:
            result = self.wiz.host.launch_xemu(_quiet)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Launch failed", str(exc))
            return
        self.status.setText(f"✔ {getattr(result, 'message', result)}  In-game: Practice → your team → formations are where you put them.")


__all__ = ["CreatePlayWizard", "DesignedFormation", "DesignedPlay", "DrawScene"]
