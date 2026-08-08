"""Structured PyQt panel for NFL 2K5's 37 private PLAY resources.

The panel combines a complete structured inspector with one bounded writer:
exact stock assignment-route copying inside the same PLAY resource.
Retail PLAY bodies and decoded names are supplied only by the user's active
source cache.  This module contains presentation logic, structural metadata,
and findings text; it never persists a playbook or contributes project edits.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Callable, Iterable, Protocol, runtime_checkable

from mod_editor.core.errors import ValidationError
from mod_editor.core.nfl2k5_playbook_inspector import (
    Nfl2k5Playbook,
    PLAY_FAMILY_LABELS,
    PlaybookFormation,
    PlaybookPlay,
    corpus_counts,
)


ProgressSink = Callable[[str, int, int], None]


PLAY_EDITOR_FINDINGS_PLAIN_TEXT = """\
Freehand route drawing is not supported
The six-hour Play Editor spike recovered a complete read-only structure, but it
did not recover enough coordinate, opcode, player-role, save-container, and
inverse-compiler semantics to write a route safely. The v1.0 product therefore
ships this structured viewer while keeping freehand Replace/Import disabled.

Safe stock-route authoring is available now
Copy Assignment Route copies an existing donor descriptor and points the target
slot at that donor's game-authored chain inside the same PLAY book. The fixed
resource size, complete chain partition, every node, formation, name, and all
non-target bytes are preserved and the complete result is reparsed. Undo,
Revert, Build, and retail-free shareable projects are supported. This is not
freehand waypoint drawing and does not invent slot roles or opcode meanings.

What is exact now
All 37 PLAY books are parsed from the user's private cache. The viewer exposes
1,533 formations, 9,251 plays, eight exact play-family values, 101,761 player
assignment references, 32,502 complete chains, and all 91,833 eight-byte nodes.
Formation links retain link slot, group, and packed value. Plays retain the
complete flags/ID word. Every assignment retains its descriptor word and chain
start. Every node retains opcode, flags, six operand bytes, and all eight raw
bytes; unknown opcodes are not given invented football meanings.

Why editing remains blocked
The eleven slot roles, formation-coordinate axes and scale, opcodes 0x01–0x1B,
operand meanings, authoring validation rules, custom-play save ownership, and a
format-preserving inverse compiler are still unknown. Guessing could turn a
route into blocking, coverage, an invalid target, or a corrupt play.

Best next spike
Create four controlled game-authored custom-play fixtures: move one receiver
only along X, move the same receiver only along Y, add one route waypoint, and
change one route type without moving its points. Diff each private save and
confirm the changed fields with runtime read watchpoints before authoring is
unlocked.

Retail-data boundary
Only parser code and these findings ship. Stock play names, formations, route
nodes, and raw PLAY resources stay in the user's private cache. Raw Export makes
a new user-owned file; shareable Mod Studio projects never contain PLAY data.
"""


PLAY_EDITOR_FINDINGS_HTML = """
<h2 style="color:#ffca80">Freehand route drawing — not supported</h2>
<p>The six-hour Play Editor spike recovered a complete read-only structure, but
not enough coordinate, opcode, player-role, save-container, or inverse-compiler
semantics to draw a new route safely. Freehand Replace/Import stays disabled.</p>
<h3 style="color:#62e6ad">Safe stock-route authoring now</h3>
<p><b>Copy Assignment Route</b> copies an exact donor descriptor and points the
target at the donor's existing chain in the same stock PLAY book. Fixed size,
the complete chain partition, all nodes, formations, names, and non-target bytes
are preserved and the result is reparsed. Undo, Revert, Build, and retail-free
projects are supported. This does not claim freehand waypoint semantics.</p>
<h3 style="color:#62e6ad">What is exact now</h3>
<p>All <b>37 PLAY books</b> are read from your private cache: 1,533 formations,
9,251 plays, eight exact play families, 101,761 assignment references, 32,502
complete chains, and all 91,833 eight-byte nodes. Link slots, groups, packed
values, complete play words, assignment descriptors, chain starts, opcodes,
flags, operands, and raw node bytes remain visible without invented meanings.</p>
<h3 style="color:#ffca80">Why editing remains blocked</h3>
<p>The eleven slot roles, coordinate axes/scale, opcode and operand meanings,
cross-record validation, custom-play save ownership, and a format-preserving
inverse compiler remain unknown. Guessing could silently turn a route into a
block, coverage assignment, invalid target, or corrupt play.</p>
<h3 style="color:#7fc8ff">Best next spike</h3>
<p>Create four controlled game-authored fixtures: X-only movement, Y-only
movement, one added waypoint, and one route-type change. Diff each private save
and confirm changed fields with runtime read watchpoints.</p>
<h3>Retail-data boundary</h3>
<p>Only parser code and status metadata ship. Stock names, formations, nodes,
and raw PLAY bodies stay in your private cache. Raw exports are user-owned files;
shareable Mod Studio projects never contain PLAY data.</p>
"""


@dataclass(frozen=True, slots=True)
class PlaybookBrowserResult:
    books: tuple[Nfl2k5Playbook, ...]
    catalog_total: int
    formation_total: int
    play_total: int
    chain_total: int
    node_total: int

    @property
    def match_total(self) -> int:
        return len(self.books)


@dataclass(frozen=True, slots=True)
class FormationPlayRow:
    link_index: int
    group: int
    packed_value: int
    play: PlaybookPlay


@dataclass(frozen=True, slots=True)
class PlaybookActionState:
    can_export: bool
    can_copy_route: bool = False
    can_revert_route: bool = False


def playbook_search_text(book: Nfl2k5Playbook) -> str:
    """Build the complete local search haystack for one decoded private book."""

    return " ".join((
        book.asset_id,
        book.book_name,
        str(book.outer_index),
        *(formation.name for formation in book.formations),
        *(play.name for play in book.plays),
        *(play.family_label for play in book.plays),
        *(category.name for category in book.categories),
    )).replace("_", " ").casefold()


def book_has_community_flags(book: Nfl2k5Playbook) -> bool:
    """True when any formation or play name matches Ace/Dime/Bear annotations."""

    names = [formation.name for formation in book.formations]
    names.extend(play.name for play in book.plays)
    return bool(broken_play_annotations(*names))


def filter_playbooks(
    books: Iterable[Nfl2k5Playbook],
    *,
    search: str = "",
    family_id: int | None = None,
    community_flagged_only: bool = False,
) -> PlaybookBrowserResult:
    """Filter decoded books without importing Qt or touching private files."""

    if family_id is not None and (
        type(family_id) is not int or not 0 <= family_id < len(PLAY_FAMILY_LABELS)
    ):
        raise ValidationError("Play family must be one of the eight decoded values.")
    rows = tuple(books)
    words = tuple(
        word for word in search.replace("_", " ").casefold().split() if word
    )
    selected = tuple(
        book for book in rows
        if (
            family_id is None
            or any(play.family_id == family_id for play in book.plays)
        )
        and (
            not words
            or all(word in playbook_search_text(book) for word in words)
        )
        and (
            not community_flagged_only
            or book_has_community_flags(book)
        )
    )
    counts = corpus_counts(rows)
    return PlaybookBrowserResult(
        books=selected,
        catalog_total=counts["books"],
        formation_total=counts["formations"],
        play_total=counts["plays"],
        chain_total=counts["chains"],
        node_total=counts["nodes"],
    )


def formation_play_rows(
    book: Nfl2k5Playbook,
    formation: PlaybookFormation | int,
) -> tuple[FormationPlayRow, ...]:
    """Resolve exact formation link metadata without losing packed fields."""

    index = formation if isinstance(formation, int) else formation.index
    if type(index) is not int or not 0 <= index < len(book.formations):
        raise ValidationError(f"Playbook {book.book_name} has no formation {index}.")
    return tuple(
        FormationPlayRow(
            link_index=link.link_index,
            group=link.group,
            packed_value=link.packed_value,
            play=book.plays[link.play_index],
        )
        for link in book.formations[index].play_links
    )


def playbook_action_state(
    book: Nfl2k5Playbook | None, *, source_ready: bool, busy: bool
) -> PlaybookActionState:
    return PlaybookActionState(
        can_export=bool(book is not None and source_ready and not busy),
        can_copy_route=bool(book is not None and source_ready and not busy),
        can_revert_route=bool(book is not None and source_ready and not busy),
    )


def suggested_playbook_filename(book: Nfl2k5Playbook) -> str:
    """Return a filesystem-safe suggestion derived from private display text."""

    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", book.book_name).strip("._-")
    return f"{book.outer_index:04d}_{stem or 'playbook'}_PLAY.bin"


def format_formation_package_map_line(
    formation_name: str, package_map: tuple[int, ...] | list[int]
) -> str:
    """Read-only one-line summary of the formation package role map for the UI.

    Package map is the 11-byte permutation at formation body ``+0x0D`` (role id
    per assignment slot). G1 offline surface; runtime package fix unproved.
    """

    if not package_map:
        return (
            "Package map: not present on this book parse "
            "(synthetic/legacy books omit +0x0D)."
        )
    if len(package_map) != 11:
        return (
            f"Package map: unexpected length {len(package_map)} "
            "(expected 11 role ids 0..10)."
        )
    values = ", ".join(str(int(v)) for v in package_map)
    line = (
        f"Package map (+0x0D): [{values}] — "
        "11 role ids (assignment slot membership). "
        "Read-only here; offline writer can patch these 11 bytes."
    )
    lowered = (formation_name or "").casefold()
    if "dime" in lowered:
        line += (
            "  ⚠ Dime: community G1 (ILB→OLB) — compare to Nickel map; "
            "runtime fix unproved."
        )
    elif "nickel" in lowered:
        line += "  Nickel reference map for G1 Dime comparisons."
    elif "ace" in lowered:
        line += (
            "  Ace: G2 TE→WR is not this map (offense packages share one map)."
        )
    return line


# Community-reported formation/package issues (APF Discord + GitHub #2).
# These are annotations only — they do not rewrite PLAY bytes. Auto-fix packs
# require offline-proved package-rule writers (see docs/product/APF_GAMEPLAY_BUG_MAP.md).
_BROKEN_PLAY_RULES: tuple[tuple[str, str, str], ...] = (
    (
        r"\bace\b",
        "Ace package",
        "Community: TE may convert to WR on long downs in game (works in practice). "
        "See APF gameplay map G2/G12 — play-link menu composition, not package map.",
    ),
    (
        r"\bdime\b",
        "Dime package",
        "Community: star ILB can be benched / treated as OLB in Dime. "
        "G1 offline surface: formation package map at +0x0D (see inspector). "
        "Runtime fix unproved — no one-click pack.",
    ),
    (
        r"\bbear\b",
        "Bear front",
        "Community: DE man on TE1 / RLB edge leftovers from 2K5-style imports. "
        "See APF gameplay map G13 — formation slot roles RE pending.",
    ),
)


@dataclass(frozen=True, slots=True)
class BrokenPlayAnnotation:
    """One honesty-labeled warning for a formation or play name."""

    code: str
    summary: str
    detail: str


def broken_play_annotations(*names: str) -> tuple[BrokenPlayAnnotation, ...]:
    """Return community broken-play flags matching any of the given names.

    Matching is case-insensitive on formation/play display names only. This never
    invents football semantics for opcodes or slot roles.
    """

    haystack = " ".join(names).casefold()
    found: list[BrokenPlayAnnotation] = []
    for pattern, code, detail in _BROKEN_PLAY_RULES:
        if re.search(pattern, haystack, flags=re.IGNORECASE):
            found.append(
                BrokenPlayAnnotation(
                    code=code,
                    summary=f"⚠ {code}",
                    detail=detail,
                )
            )
    return tuple(found)


def format_play_name_with_warnings(play_name: str, *extra_names: str) -> str:
    """Append short ⚠ tags for known community-broken packages."""

    notes = broken_play_annotations(play_name, *extra_names)
    if not notes:
        return play_name
    tags = " ".join(note.summary for note in notes)
    return f"{play_name}  {tags}"


@runtime_checkable
class PlaybooksPanelHost(Protocol):
    """Complete source-bound facade surface consumed by the viewer."""

    @property
    def source_ready(self) -> bool: ...

    @property
    def playbook_available(self) -> bool: ...

    def browse_playbooks(
        self, search: str, progress: ProgressSink
    ) -> Iterable[Nfl2k5Playbook]: ...

    def export_playbook(
        self, asset_id: str, destination: Path, progress: ProgressSink
    ) -> Path: ...

    def export_playbook_link_table_copy(
        self,
        asset_id: str,
        target_formation_index: int,
        donor_formation_index: int,
        destination: Path,
        progress: ProgressSink,
    ) -> Path: ...

    def export_playbook_package_map_copy(
        self,
        asset_id: str,
        target_formation_index: int,
        donor_formation_index: int,
        destination: Path,
        progress: ProgressSink,
    ) -> Path: ...

    def copy_play_assignment_route(
        self, asset_id: str, target_play_index: int, target_slot_index: int,
        donor_play_index: int, donor_slot_index: int, progress: ProgressSink,
    ) -> object: ...

    def revert_play_assignment_route(
        self, asset_id: str, target_play_index: int, target_slot_index: int,
        progress: ProgressSink,
    ) -> object: ...

    def create_formation(
        self, asset_id: str, donor_formation_index: int, progress: ProgressSink,
    ) -> object: ...

    def create_play(
        self, asset_id: str, donor_play_index: int, progress: ProgressSink,
    ) -> object: ...

    def revert_formation_create(self, selector: str, progress: ProgressSink) -> object: ...
    def revert_play_create(self, selector: str, progress: ProgressSink) -> object: ...


from PyQt5.QtCore import QObject, QRunnable, Qt, QThreadPool, QTimer, pyqtSignal
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QFrame,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)


class _TaskSignals(QObject):
    result = pyqtSignal(object)
    error = pyqtSignal(str)
    progress = pyqtSignal(str, int, int)
    finished = pyqtSignal()


class _Task(QRunnable):
    def __init__(self, operation: Callable[[ProgressSink], object]) -> None:
        super().__init__()
        self.operation = operation
        self.signals = _TaskSignals()
        self.setAutoDelete(False)

    def run(self) -> None:
        try:
            result = self.operation(self.signals.progress.emit)
        except BaseException as exc:
            self.signals.error.emit(str(exc).strip() or exc.__class__.__name__)
        else:
            self.signals.result.emit(result)
        finally:
            self.signals.finished.emit()


class PlaybooksPanel(QWidget):
    """Structured viewer plus exact stock route-copy authoring."""

    error_raised = pyqtSignal(str)

    def __init__(self, host: PlaybooksPanelHost, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        if not isinstance(host, PlaybooksPanelHost):
            raise TypeError("Playbooks panel host does not implement PlaybooksPanelHost")
        self.host = host
        self._all_books: tuple[Nfl2k5Playbook, ...] = ()
        self.browser = PlaybookBrowserResult((), 0, 0, 0, 0, 0)
        self.selected_asset_id: str | None = None
        self._visible_play_rows: tuple[FormationPlayRow, ...] = ()
        self._busy = False
        self._loaded = False
        self._refresh_after_task = False
        self._generation = 0
        self._tasks: set[_Task] = set()
        self._pool = QThreadPool(self)
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(180)
        self._search_timer.timeout.connect(self._apply_filters)
        self.setObjectName("playbooksPanel")
        self._build_ui()
        self._apply_style()
        self._connect()
        self.reset_for_source()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 22)
        root.setSpacing(12)

        header = QHBoxLayout()
        titles = QVBoxLayout()
        title = QLabel("Playbooks & Plays")
        title.setObjectName("playTitle")
        subtitle = QLabel(
            "Inspect every stock book, formation, family, player assignment, "
            "and exact raw node chain from your own XISO."
        )
        subtitle.setObjectName("playMuted")
        subtitle.setWordWrap(True)
        titles.addWidget(title)
        titles.addWidget(subtitle)
        self.count_label = QLabel("Load XISO")
        self.count_label.setObjectName("playCountPill")
        header.addLayout(titles, 1)
        header.addWidget(self.count_label)
        root.addLayout(header)

        boundary = QLabel(
            "FREEHAND WAYPOINT DRAWING — NOT SUPPORTED  •  Copy an existing stock "
            "assignment route safely, then Undo, Revert, save a project, or Build."
        )
        boundary.setObjectName("playBoundary")
        boundary.setWordWrap(True)
        root.addWidget(boundary)

        splitter = QSplitter(Qt.Horizontal)
        browser_card = QFrame()
        browser_card.setObjectName("playCard")
        browser_layout = QVBoxLayout(browser_card)
        browser_layout.setContentsMargins(14, 14, 14, 14)
        browser_layout.setSpacing(9)
        self.search = QLineEdit()
        self.search.setClearButtonEnabled(True)
        self.search.setAccessibleName("Search playbooks")
        self.search.setProperty("studioSearch", True)
        self.search.setPlaceholderText(
            "Search book, formation, play… (try Ace, Dime, Bear)  · Ctrl+F"
        )
        self.search.setToolTip(
            "Filters stock books by name metadata. Formations named Ace/Dime/Bear "
            "show ⚠ community annotations in the inspector (discovery only)."
        )
        self.family_filter = QComboBox()
        self.family_filter.addItem("All eight play families", None)
        for family_id, label in enumerate(PLAY_FAMILY_LABELS):
            self.family_filter.addItem(label, family_id)
        self.warning_filter = QComboBox()
        self.warning_filter.addItem("All formations", "all")
        self.warning_filter.addItem("⚠ Community-flagged only (Ace/Dime/Bear)", "flagged")
        self.warning_filter.setToolTip(
            "Show only books that contain Ace, Dime, or Bear package names "
            "flagged by community reports (G1/G2/G13). Does not rewrite PLAY bytes."
        )
        browser_layout.addWidget(self.search)
        browser_layout.addWidget(self.family_filter)
        browser_layout.addWidget(self.warning_filter)
        self.community_legend = QLabel(
            "Community flags (annotations only — no auto-fix packs): "
            "⚠ Ace = G2 TE→WR on long downs · "
            "⚠ Dime = G1 ILB→OLB role map · "
            "⚠ Bear = G13 DE/RLB leftovers. "
            "Use Export Package-Map / Link-Table Copy for offline experimental "
            "PLAY bytes (runtime unproved)."
        )
        self.community_legend.setObjectName("playMuted")
        self.community_legend.setWordWrap(True)
        self.community_legend.setToolTip(
            "Full map: docs/product/APF_GAMEPLAY_BUG_MAP.md (G1–G14). "
            "Discovery in this panel only rewrites nothing on your disc."
        )
        browser_layout.addWidget(self.community_legend)
        self.book_table = QTableWidget(0, 3)
        self.book_table.setHorizontalHeaderLabels(("Book", "Formations", "Plays"))
        self.book_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.book_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.book_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.book_table.setAlternatingRowColors(True)
        self.book_table.verticalHeader().setVisible(False)
        book_header = self.book_table.horizontalHeader()
        book_header.setSectionResizeMode(0, QHeaderView.Stretch)
        book_header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        book_header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        browser_layout.addWidget(self.book_table, 1)
        self.match_label = QLabel("Load your XISO to inspect 37 books")
        self.match_label.setObjectName("playMuted")
        browser_layout.addWidget(self.match_label)
        splitter.addWidget(browser_card)

        self.tabs = QTabWidget()
        inspector = QWidget()
        inspector_layout = QVBoxLayout(inspector)
        inspector_layout.setContentsMargins(14, 12, 14, 12)
        inspector_layout.setSpacing(9)
        detail_header = QHBoxLayout()
        detail_titles = QVBoxLayout()
        self.book_title = QLabel("Select a playbook")
        self.book_title.setObjectName("playDetailTitle")
        self.book_meta = QLabel(
            "PLAY data is read lazily from the private cache and never added to projects."
        )
        self.book_meta.setObjectName("playMuted")
        self.book_meta.setWordWrap(True)
        detail_titles.addWidget(self.book_title)
        detail_titles.addWidget(self.book_meta)
        self.export_button = QPushButton("Export Selected Raw PLAY")
        self.export_button.setObjectName("playPrimaryButton")
        detail_header.addLayout(detail_titles, 1)
        detail_header.addWidget(self.export_button)
        inspector_layout.addLayout(detail_header)

        formation_row = QHBoxLayout()
        formation_label = QLabel("Formation")
        formation_label.setObjectName("playFieldLabel")
        self.formation_combo = QComboBox()
        self.formation_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        formation_row.addWidget(formation_label)
        formation_row.addWidget(self.formation_combo, 1)
        inspector_layout.addLayout(formation_row)

        self.package_map_label = QLabel(
            "Package map: select a formation to show the 11-byte role map (+0x0D)."
        )
        self.package_map_label.setObjectName("playMuted")
        self.package_map_label.setWordWrap(True)
        self.package_map_label.setToolTip(
            "Formation body offset +0x0D holds an 11-byte package role map "
            "(permutation of 0..10). Dime vs Nickel differ here (G1 offline "
            "surface). Read-only in this panel; offline writer is separate. "
            "Runtime G1 fix is unproved."
        )
        inspector_layout.addWidget(self.package_map_label)

        self.play_table = QTableWidget(0, 6)
        self.play_table.setHorizontalHeaderLabels(
            ("Link", "Group", "Play", "Name", "Family", "Full word")
        )
        self._configure_table(self.play_table, stretch_column=3)
        self.play_table.setMinimumHeight(210)
        inspector_layout.addWidget(self.play_table, 4)

        self.play_meta = QLabel(
            "Choose a formation play to expose all eleven assignment descriptors."
        )
        self.play_meta.setObjectName("playRawNote")
        self.play_meta.setWordWrap(True)
        inspector_layout.addWidget(self.play_meta)

        route_row = QHBoxLayout()
        route_label = QLabel("Copy selected target from")
        route_label.setObjectName("playFieldLabel")
        self.donor_play_combo = QComboBox()
        self.donor_play_combo.setToolTip(
            "Choose a donor play in this same stock PLAY book."
        )
        self.donor_slot_combo = QComboBox()
        for slot in range(11):
            self.donor_slot_combo.addItem(f"Slot {slot}", slot)
        self.copy_route_button = QPushButton("Copy Assignment Route")
        self.copy_route_button.setObjectName("playPrimaryButton")
        self.revert_route_button = QPushButton("Revert Selected Route")
        route_row.addWidget(route_label)
        route_row.addWidget(self.donor_play_combo, 1)
        route_row.addWidget(self.donor_slot_combo)
        route_row.addWidget(self.copy_route_button)
        route_row.addWidget(self.revert_route_button)
        inspector_layout.addLayout(route_row)

        create_row = QHBoxLayout()
        create_label = QLabel("Create new as clone:")
        create_label.setObjectName("playFieldLabel")
        self.create_formation_button = QPushButton("Create Formation")
        self.create_play_button = QPushButton("Create Play")
        self.create_formation_button.setToolTip("Clone the selected formation into a new slot (reuses name, bumps count).")
        self.create_play_button.setToolTip("Clone the selected play into a new slot (reuses name, 11 assignments, bumps count).")
        create_row.addWidget(create_label)
        create_row.addWidget(self.create_formation_button)
        create_row.addWidget(self.create_play_button)
        create_row.addStretch(1)
        inspector_layout.addLayout(create_row)

        # Experimental G2-class menu composition export (offline only).
        self.link_copy_banner = QLabel(
            "⚠ Experimental offline export only — copies another formation’s "
            "play-link menu (aux table) onto the selected formation and writes "
            "a private PLAY file. Does not stage a project edit. Does not claim "
            "a runtime G2 (TE→WR) or G1 fix. Source ISO is never modified."
        )
        self.link_copy_banner.setObjectName("playBoundary")
        self.link_copy_banner.setWordWrap(True)
        inspector_layout.addWidget(self.link_copy_banner)

        link_copy_row = QHBoxLayout()
        link_copy_label = QLabel("Export menu copy from donor:")
        link_copy_label.setObjectName("playFieldLabel")
        self.link_donor_combo = QComboBox()
        self.link_donor_combo.setToolTip(
            "Donor formation whose play-link menu is copied onto the selected "
            "formation in the exported PLAY only."
        )
        self.export_link_copy_button = QPushButton("Export Link-Table Copy…")
        self.export_link_copy_button.setToolTip(
            "Build a private PLAY with the selected formation’s menu replaced "
            "by the donor’s. Offline-writer-proved bytes only; runtime unproved."
        )
        self.export_pkgmap_copy_button = QPushButton("Export Package-Map Copy…")
        self.export_pkgmap_copy_button.setToolTip(
            "Build a private PLAY with the selected formation’s +0x0D package "
            "map replaced by the donor’s (G1 Dime/Nickel surface). Offline only; "
            "runtime unproved."
        )
        link_copy_row.addWidget(link_copy_label)
        link_copy_row.addWidget(self.link_donor_combo, 1)
        link_copy_row.addWidget(self.export_link_copy_button)
        link_copy_row.addWidget(self.export_pkgmap_copy_button)
        inspector_layout.addLayout(link_copy_row)

        raw_split = QSplitter(Qt.Horizontal)
        self.assignment_table = QTableWidget(0, 5)
        self.assignment_table.setHorizontalHeaderLabels(
            ("Slot", "Descriptor", "Chain start", "Extent", "Nodes")
        )
        self._configure_table(self.assignment_table, stretch_column=1)
        self.assignment_table.setToolTip(
            "Slot roles remain unknown; descriptor words are shown exactly."
        )
        raw_split.addWidget(self.assignment_table)
        self.node_table = QTableWidget(0, 6)
        self.node_table.setHorizontalHeaderLabels(
            ("Node", "Opcode", "Flags", "Operands (6 bytes)", "Raw 8 bytes", "End")
        )
        self._configure_table(self.node_table, stretch_column=4)
        self.node_table.setToolTip(
            "Opcodes and operands remain semantic unknowns and are not renamed."
        )
        raw_split.addWidget(self.node_table)
        raw_split.setStretchFactor(0, 4)
        raw_split.setStretchFactor(1, 6)
        inspector_layout.addWidget(raw_split, 5)
        self.tabs.addTab(inspector, "Structured inspector")

        findings = QTextBrowser()
        findings.setObjectName("playFindings")
        findings.setOpenExternalLinks(False)
        findings.setHtml(PLAY_EDITOR_FINDINGS_HTML)
        self.tabs.addTab(findings, "Editing boundary")
        splitter.addWidget(self.tabs)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 7)
        root.addWidget(splitter, 1)

        progress_row = QHBoxLayout()
        self.progress_label = QLabel("Ready")
        self.progress_label.setObjectName("playMuted")
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedWidth(180)
        self.progress_bar.hide()
        progress_row.addWidget(self.progress_label)
        progress_row.addStretch(1)
        progress_row.addWidget(self.progress_bar)
        root.addLayout(progress_row)

    @staticmethod
    def _configure_table(table: QTableWidget, *, stretch_column: int) -> None:
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        header = table.horizontalHeader()
        for column in range(table.columnCount()):
            header.setSectionResizeMode(
                column,
                QHeaderView.Stretch
                if column == stretch_column else QHeaderView.ResizeToContents,
            )

    def _connect(self) -> None:
        self.search.textChanged.connect(lambda _text: self._search_timer.start())
        self.family_filter.currentIndexChanged.connect(self._apply_filters)
        self.warning_filter.currentIndexChanged.connect(self._apply_filters)
        self.book_table.itemSelectionChanged.connect(self._book_selected)
        self.formation_combo.currentIndexChanged.connect(self._formation_selected)
        self.play_table.itemSelectionChanged.connect(self._play_selected)
        self.assignment_table.itemSelectionChanged.connect(self._assignment_selected)
        self.export_button.clicked.connect(self._export_selected)
        self.copy_route_button.clicked.connect(self._copy_selected_route)
        self.revert_route_button.clicked.connect(self._revert_selected_route)
        self.create_formation_button.clicked.connect(self._create_formation)
        self.export_link_copy_button.clicked.connect(self._export_link_table_copy)
        self.export_pkgmap_copy_button.clicked.connect(self._export_package_map_copy)
        self.link_donor_combo.currentIndexChanged.connect(
            lambda _i: self._refresh_controls()
        )
        self.create_play_button.clicked.connect(self._create_play)
        self.donor_play_combo.currentIndexChanged.connect(self._refresh_controls)
        self.donor_slot_combo.currentIndexChanged.connect(self._refresh_controls)
        self.formation_combo.currentIndexChanged.connect(lambda _i: self._refresh_controls())
        self.error_raised.connect(
            lambda message: QMessageBox.warning(self, "Playbooks & Plays", message)
        )

    def reset_for_source(self) -> None:
        """Drop all decoded private values before a different source is used."""

        self._generation += 1
        self._loaded = False
        self._all_books = ()
        self.browser = PlaybookBrowserResult((), 0, 0, 0, 0, 0)
        self.selected_asset_id = None
        self._visible_play_rows = ()
        for table in (
            self.book_table, self.play_table, self.assignment_table, self.node_table
        ):
            table.clearContents()
            table.setRowCount(0)
        self.formation_combo.clear()
        self.donor_play_combo.clear()
        self.book_title.setText("Select a playbook")
        self.book_meta.setText(
            "Load your NFL 2K5 XISO to read the 37 private PLAY resources."
        )
        self.count_label.setText("Load XISO")
        self.match_label.setText("Load your XISO to inspect 37 books")
        self.progress_label.setText("Ready")
        self._refresh_controls()

    def refresh(self, *, force: bool = False) -> None:
        if not self.host.source_ready or not self.host.playbook_available:
            self.reset_for_source()
            return
        if self._loaded and not force:
            self._apply_filters()
            return
        if self._busy:
            self._refresh_after_task = True
            return
        self._generation += 1
        generation = self._generation

        def ready(value: object) -> None:
            if generation != self._generation:
                return
            books = tuple(value)  # type: ignore[arg-type]
            if len(books) != 37 or not all(
                isinstance(book, Nfl2k5Playbook) for book in books
            ):
                self.error_raised.emit(
                    "The active source did not return the expected 37 playbooks."
                )
                return
            self._all_books = books
            self._loaded = True
            self.progress_label.setText("Structured PLAY viewer ready")
            self._apply_filters()

        self._run(
            lambda progress: tuple(self.host.browse_playbooks("", progress)),
            ready,
        )

    def _apply_filters(self, *_args: object) -> None:
        wanted = self.selected_asset_id
        try:
            self.browser = filter_playbooks(
                self._all_books,
                search=self.search.text(),
                family_id=self.family_filter.currentData(),
                community_flagged_only=(
                    self.warning_filter.currentData() == "flagged"
                ),
            )
        except Exception as exc:
            self.error_raised.emit(str(exc).strip() or exc.__class__.__name__)
            return
        self.book_table.blockSignals(True)
        self.book_table.clearContents()
        self.book_table.setRowCount(len(self.browser.books))
        selected_row = -1
        for row, book in enumerate(self.browser.books):
            values = (book.book_name, str(len(book.formations)), str(len(book.plays)))
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.UserRole, book.asset_id)
                if column == 0:
                    item.setToolTip(book.asset_id)
                self.book_table.setItem(row, column, item)
            if book.asset_id == wanted:
                selected_row = row
        if selected_row < 0 and self.browser.books:
            selected_row = 0
        self.book_table.blockSignals(False)
        self.count_label.setText(
            f"{self.browser.catalog_total:,} books · "
            f"{self.browser.play_total:,} plays · {self.browser.node_total:,} nodes"
        )
        flagged = self.warning_filter.currentData() == "flagged"
        if self.browser.match_total == 0 and flagged:
            self.match_label.setText(
                "0 matching books under ⚠ Community-flagged. "
                "Load a full XISO, clear the search box, or switch to "
                "“All formations” — Ace/Dime/Bear names live inside stock books "
                "once PLAY metadata is indexed."
            )
        elif self.browser.match_total == 0:
            self.match_label.setText(
                "0 matching books. Clear search/family filters, or load your "
                "NFL 2K5 XISO if the catalog is empty."
            )
        else:
            self.match_label.setText(
                f"{self.browser.match_total:,} matching book"
                f"{'s' if self.browser.match_total != 1 else ''} · "
                f"{self.browser.formation_total:,} formations · "
                f"{self.browser.chain_total:,} exact chains"
            )
        if selected_row >= 0:
            self.book_table.selectRow(selected_row)
            self._book_selected()
        else:
            self.selected_asset_id = None
            self._show_book(None)

    def _selected_book(self) -> Nfl2k5Playbook | None:
        if self.selected_asset_id is None:
            return None
        return next(
            (book for book in self._all_books if book.asset_id == self.selected_asset_id),
            None,
        )

    def _book_selected(self) -> None:
        rows = self.book_table.selectionModel().selectedRows()
        if not rows:
            self.selected_asset_id = None
            self._show_book(None)
            return
        item = self.book_table.item(rows[0].row(), 0)
        self.selected_asset_id = str(item.data(Qt.UserRole))
        self._show_book(self._selected_book())

    def _show_book(self, book: Nfl2k5Playbook | None) -> None:
        self.formation_combo.blockSignals(True)
        self.formation_combo.clear()
        if book is None:
            self.book_title.setText("No playbook selected")
            flagged = (
                hasattr(self, "warning_filter")
                and self.warning_filter.currentData() == "flagged"
            )
            if flagged:
                self.book_meta.setText(
                    "No ⚠ Ace/Dime/Bear books match this filter. "
                    "Clear the community-flagged filter or search, load your XISO, "
                    "then open a stock book and inspect package-map lines for G1."
                )
            else:
                self.book_meta.setText(
                    "Broaden the search or choose another family. "
                    "Try Ace, Dime, or Bear in the search box for community flags."
                )
            self.formation_combo.blockSignals(False)
            self._clear_structure()
            self._refresh_controls()
            return
        self.book_title.setText(book.book_name)
        categories = ", ".join(category.name for category in book.categories)
        self.book_meta.setText(
            f"Outer entry {book.outer_index} · {len(book.formations):,} formations · "
            f"{len(book.plays):,} plays · {len(book.chains):,} exact chains · "
            f"{book.node_count:,} nodes\n{book.asset_id}\n"
            f"Categories: {categories or 'none declared'}"
        )
        for formation in book.formations:
            formation_label = format_play_name_with_warnings(formation.name)
            self.formation_combo.addItem(
                f"{formation.index:02d} · {formation_label} "
                f"({len(formation.play_links)} linked plays)",
                formation.index,
            )
        self.donor_play_combo.blockSignals(True)
        self.donor_play_combo.clear()
        for play in book.plays:
            self.donor_play_combo.addItem(
                f"Play {play.index} · {play.name} · {play.family_label}",
                play.index,
            )
        self.donor_play_combo.blockSignals(False)
        self.link_donor_combo.blockSignals(True)
        self.link_donor_combo.clear()
        for formation in book.formations:
            self.link_donor_combo.addItem(
                f"{formation.index:02d} · {formation.name} "
                f"({len(formation.play_links)} links)",
                formation.index,
            )
        self.link_donor_combo.blockSignals(False)
        self.formation_combo.blockSignals(False)
        if book.formations:
            self.formation_combo.setCurrentIndex(0)
            self._formation_selected()
        else:
            self._clear_structure()
        self._refresh_controls()

    def _clear_structure(self) -> None:
        self._visible_play_rows = ()
        for table in (self.play_table, self.assignment_table, self.node_table):
            table.clearContents()
            table.setRowCount(0)
        self.play_meta.setText(
            "Choose a formation play to expose all eleven assignment descriptors."
        )
        self.package_map_label.setText(
            "Package map: select a formation to show the 11-byte role map (+0x0D)."
        )

    def _formation_selected(self, *_args: object) -> None:
        book = self._selected_book()
        formation_index = self.formation_combo.currentData()
        if book is None or formation_index is None:
            self._clear_structure()
            return
        formation = book.formations[int(formation_index)]
        self.package_map_label.setText(
            format_formation_package_map_line(
                formation.name, formation.package_map
            )
        )
        self._visible_play_rows = formation_play_rows(book, int(formation_index))
        self.play_table.blockSignals(True)
        self.play_table.clearContents()
        self.play_table.setRowCount(len(self._visible_play_rows))
        formation_name = ""
        if book is not None and formation_index is not None:
            formation_name = book.formations[int(formation_index)].name
        for row, linked in enumerate(self._visible_play_rows):
            display_name = format_play_name_with_warnings(
                linked.play.name, formation_name
            )
            values = (
                str(linked.link_index),
                str(linked.group),
                str(linked.play.index),
                display_name,
                f"{linked.play.family_id} · {linked.play.family_label}",
                f"0x{linked.play.flags_or_id:08x}",
            )
            warnings = broken_play_annotations(linked.play.name, formation_name)
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.UserRole, row)
                if column == 0:
                    item.setToolTip(f"Packed formation value 0x{linked.packed_value:04x}")
                if column == 3 and warnings:
                    item.setToolTip("\n\n".join(note.detail for note in warnings))
                self.play_table.setItem(row, column, item)
        self.play_table.blockSignals(False)
        self.assignment_table.setRowCount(0)
        self.node_table.setRowCount(0)
        if self._visible_play_rows:
            self.play_table.selectRow(0)
            self._play_selected()
        else:
            self.play_meta.setText("This formation has no active play links.")

    def _selected_linked_play(self) -> FormationPlayRow | None:
        rows = self.play_table.selectionModel().selectedRows()
        if not rows:
            return None
        index = rows[0].row()
        return (
            self._visible_play_rows[index]
            if 0 <= index < len(self._visible_play_rows) else None
        )

    def _play_selected(self) -> None:
        book = self._selected_book()
        linked = self._selected_linked_play()
        if book is None or linked is None:
            self.assignment_table.setRowCount(0)
            self.node_table.setRowCount(0)
            return
        play = linked.play
        self.play_meta.setText(
            f"Play {play.index} · family {play.family_id} ({play.family_label}) · "
            f"full flags/ID word 0x{play.flags_or_id:08x} · formation link "
            f"{linked.link_index} / group {linked.group} / packed "
            f"0x{linked.packed_value:04x}. Slot roles remain unknown."
        )
        self.assignment_table.blockSignals(True)
        self.assignment_table.clearContents()
        self.assignment_table.setRowCount(len(play.assignments))
        for row, assignment in enumerate(play.assignments):
            chain = book.chain(assignment.chain_start_index)
            values = (
                str(assignment.slot_index),
                f"0x{assignment.descriptor_word:08x}",
                str(assignment.chain_start_index),
                f"{chain.start_index}–{chain.end_index - 1}",
                str(chain.node_count),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.UserRole, assignment.chain_start_index)
                self.assignment_table.setItem(row, column, item)
        self.assignment_table.blockSignals(False)
        donor_index = self.donor_play_combo.findData(play.index)
        if donor_index >= 0:
            self.donor_play_combo.setCurrentIndex(donor_index)
        if play.assignments:
            self.assignment_table.selectRow(0)
            self._assignment_selected()

    def _assignment_selected(self) -> None:
        book = self._selected_book()
        rows = self.assignment_table.selectionModel().selectedRows()
        if book is None or not rows:
            self.node_table.setRowCount(0)
            return
        item = self.assignment_table.item(rows[0].row(), 0)
        start_index = int(item.data(Qt.UserRole))
        chain = book.chain(start_index)
        self.node_table.clearContents()
        self.node_table.setRowCount(len(chain.nodes))
        for row, node in enumerate(chain.nodes):
            values = (
                str(node.index),
                f"0x{node.opcode:02x}",
                f"0x{node.flags:02x}",
                node.operands_hex,
                node.raw_hex,
                "yes" if node.ends_chain else "",
            )
            for column, value in enumerate(values):
                self.node_table.setItem(row, column, QTableWidgetItem(value))
        linked = self._selected_linked_play()
        target_slot = rows[0].row()
        if (
            linked is not None
            and self.donor_play_combo.currentData() == linked.play.index
            and self.donor_slot_combo.currentData() == target_slot
        ):
            self.donor_slot_combo.setCurrentIndex((target_slot + 1) % 11)
        self._refresh_controls()

    def _refresh_controls(self) -> None:
        state = playbook_action_state(
            self._selected_book(),
            source_ready=self.host.source_ready,
            busy=self._busy,
        )
        self.export_button.setEnabled(state.can_export)
        linked = self._selected_linked_play()
        assignment_rows = self.assignment_table.selectionModel().selectedRows()
        target_slot = assignment_rows[0].row() if assignment_rows else None
        donor_play = self.donor_play_combo.currentData()
        donor_slot = self.donor_slot_combo.currentData()
        different = bool(
            linked is not None and target_slot is not None
            and (linked.play.index, target_slot) != (donor_play, donor_slot)
        )
        self.copy_route_button.setEnabled(state.can_copy_route and different)
        self.revert_route_button.setEnabled(
            state.can_revert_route and linked is not None and target_slot is not None
        )
        # Formation/play creation: enabled when a book is selected, source ready, not busy, and capacity not full
        book = self._selected_book()
        can_create = bool(book is not None and self.host.source_ready and not self._busy)
        formation_full = bool(book is not None and len(book.formations) >= 50)
        play_full = bool(book is not None and len(book.plays) >= 270)
        self.create_formation_button.setEnabled(can_create and not formation_full and self.formation_combo.currentData() is not None)
        self.create_play_button.setEnabled(can_create and not play_full and linked is not None)
        if formation_full:
            self.create_formation_button.setToolTip("Formation capacity 50 reached — cannot create more in this book.")
        else:
            self.create_formation_button.setToolTip("Clone the selected formation into a new slot (reuses name, bumps count).")
        if play_full:
            self.create_play_button.setToolTip("Play capacity 270 reached — cannot create more in this book.")
        else:
            self.create_play_button.setToolTip("Clone the selected play into a new slot (reuses name, 11 assignments, bumps count).")
        target_form = self.formation_combo.currentData()
        donor_form = self.link_donor_combo.currentData()
        can_link_export = bool(
            can_create
            and target_form is not None
            and donor_form is not None
            and int(target_form) != int(donor_form)
        )
        # Never silent-gray: G1/G2 experimental exports stay clickable and explain.
        if can_link_export:
            link_tip = (
                "Export a private PLAY where the selected formation’s play-link "
                "menu is replaced by the donor’s. Offline only; runtime unproved."
            )
            pkg_tip = (
                "Export a private PLAY where the selected formation’s package map "
                "(+0x0D) is replaced by the donor’s. G1 surface; runtime unproved."
            )
            block = ""
        elif not self.host.source_ready:
            block = (
                "Load your NFL 2K5 XISO first. Experimental G1/G2 exports need a "
                "source. Click still explains — buttons stay clickable."
            )
            link_tip = pkg_tip = block
        elif target_form is not None and donor_form is not None:
            block = "Pick a donor formation different from the selected target."
            link_tip = pkg_tip = block
        else:
            block = (
                "Select a book and two different formations (target + donor) to "
                "export an experimental offline PLAY copy. Runtime G1/G2 unproved."
            )
            link_tip = pkg_tip = block
        self.export_link_copy_button.setEnabled(True)
        self.export_pkgmap_copy_button.setEnabled(True)
        self.export_link_copy_button.setToolTip(link_tip)
        self.export_pkgmap_copy_button.setToolTip(pkg_tip)
        self.export_link_copy_button.setProperty("disableReason", block)
        self.export_pkgmap_copy_button.setProperty("disableReason", block)
        self.link_donor_combo.setEnabled(can_create)
        self.book_table.setEnabled(not self._busy)
        self.search.setEnabled(not self._busy)
        self.family_filter.setEnabled(not self._busy)
        self.donor_play_combo.setEnabled(not self._busy)
        self.donor_slot_combo.setEnabled(not self._busy)

    def _selected_route_target(self) -> tuple[Nfl2k5Playbook, int, int] | None:
        book = self._selected_book()
        linked = self._selected_linked_play()
        rows = self.assignment_table.selectionModel().selectedRows()
        if book is None or linked is None or not rows:
            return None
        return book, linked.play.index, rows[0].row()

    def _copy_selected_route(self) -> None:
        target = self._selected_route_target()
        donor_play = self.donor_play_combo.currentData()
        donor_slot = self.donor_slot_combo.currentData()
        if target is None or donor_play is None or donor_slot is None:
            return
        book, target_play, target_slot = target

        def ready(_value: object) -> None:
            self.progress_label.setText(
                f"Copied stock route to play {target_play}, slot {target_slot}"
            )

        self._run(
            lambda progress: self.host.copy_play_assignment_route(
                book.asset_id, target_play, target_slot,
                int(donor_play), int(donor_slot), progress,
            ),
            ready,
        )

    def _revert_selected_route(self) -> None:
        target = self._selected_route_target()
        if target is None:
            return
        book, target_play, target_slot = target

        def ready(_value: object) -> None:
            self.progress_label.setText(
                f"Reverted route at play {target_play}, slot {target_slot}"
            )

        self._run(
            lambda progress: self.host.revert_play_assignment_route(
                book.asset_id, target_play, target_slot, progress,
            ),
            ready,
        )

    def _create_formation(self) -> None:
        book = self._selected_book()
        donor_idx = self.formation_combo.currentData()
        if book is None or donor_idx is None:
            return

        def ready(_value: object) -> None:
            self.progress_label.setText(f"Created formation from {book.formations[donor_idx].name} — refresh to see new slot {len(book.formations)}")
            self._refresh_after_task = True

        self._run(
            lambda progress: self.host.create_formation(book.asset_id, int(donor_idx), progress),
            ready,
        )

    def _export_link_table_copy(self) -> None:
        reason = str(
            self.export_link_copy_button.property("disableReason") or ""
        ).strip()
        if reason:
            QMessageBox.information(
                self,
                "Cannot export link-table copy yet",
                reason
                + "\n\nFix: load XISO → open a playbook → pick two different "
                "formations (target + donor). Export is offline-only; runtime G2 "
                "unproved.",
            )
            return
        book = self._selected_book()
        target_idx = self.formation_combo.currentData()
        donor_idx = self.link_donor_combo.currentData()
        if book is None or target_idx is None or donor_idx is None:
            return
        if int(target_idx) == int(donor_idx):
            QMessageBox.information(
                self,
                "Pick a different donor",
                "The donor formation must differ from the selected target "
                "formation. No file was written.",
            )
            return
        target_name = book.formations[int(target_idx)].name
        donor_name = book.formations[int(donor_idx)].name
        answer = QMessageBox.warning(
            self,
            "Experimental offline export only",
            f"This will write a private PLAY file where formation "
            f"“{target_name}” gets the play-link menu from “{donor_name}”.\n\n"
            "• Not a project edit — nothing is staged for Build.\n"
            "• Not a runtime G2 (TE→WR) or G1 fix — unproved in-game.\n"
            "• Your loaded source / ISO is never modified.\n\n"
            "Continue to choose a save location?",
            QMessageBox.Yes | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )
        if answer != QMessageBox.Yes:
            return
        suggested = (
            f"{book.outer_index:04d}_{book.book_name}_"
            f"{target_name}_menu_from_{donor_name}_PLAY.bin"
        )
        suggested = re.sub(r"[^A-Za-z0-9._-]+", "_", suggested)
        path, _filter = QFileDialog.getSaveFileName(
            self,
            "Export experimental link-table PLAY",
            suggested,
            "PLAY resource (*.bin);;All files (*)",
        )
        if not path:
            return

        def ready(value: object) -> None:
            self.progress_label.setText(
                f"Exported experimental menu copy → {value} "
                f"({target_name} ← {donor_name}; runtime unproved)"
            )

        self._run(
            lambda progress: self.host.export_playbook_link_table_copy(
                book.asset_id,
                int(target_idx),
                int(donor_idx),
                Path(path),
                progress,
            ),
            ready,
        )

    def _export_package_map_copy(self) -> None:
        reason = str(
            self.export_pkgmap_copy_button.property("disableReason") or ""
        ).strip()
        if reason:
            QMessageBox.information(
                self,
                "Cannot export package-map copy yet",
                reason
                + "\n\nFix: load XISO → open a playbook → pick two different "
                "formations (target + donor). G1 offline surface only; runtime "
                "ILB fix unproved.",
            )
            return
        book = self._selected_book()
        target_idx = self.formation_combo.currentData()
        donor_idx = self.link_donor_combo.currentData()
        if book is None or target_idx is None or donor_idx is None:
            return
        if int(target_idx) == int(donor_idx):
            QMessageBox.information(
                self,
                "Pick a different donor",
                "The donor formation must differ from the selected target "
                "formation. No file was written.",
            )
            return
        target_name = book.formations[int(target_idx)].name
        donor_name = book.formations[int(donor_idx)].name
        answer = QMessageBox.warning(
            self,
            "Experimental offline export only",
            f"This will write a private PLAY file where formation "
            f"“{target_name}” gets the package map (+0x0D) from “{donor_name}”.\n\n"
            "• G1 offline surface (Dime/Nickel class) — runtime ILB fix unproved.\n"
            "• Not a project edit — nothing is staged for Build.\n"
            "• Your loaded source / ISO is never modified.\n\n"
            "Continue to choose a save location?",
            QMessageBox.Yes | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )
        if answer != QMessageBox.Yes:
            return
        suggested = (
            f"{book.outer_index:04d}_{book.book_name}_"
            f"{target_name}_pkgmap_from_{donor_name}_PLAY.bin"
        )
        suggested = re.sub(r"[^A-Za-z0-9._-]+", "_", suggested)
        path, _filter = QFileDialog.getSaveFileName(
            self,
            "Export experimental package-map PLAY",
            suggested,
            "PLAY resource (*.bin);;All files (*)",
        )
        if not path:
            return

        def ready(value: object) -> None:
            self.progress_label.setText(
                f"Exported experimental package-map copy → {value} "
                f"({target_name} ← {donor_name}; runtime unproved)"
            )

        self._run(
            lambda progress: self.host.export_playbook_package_map_copy(
                book.asset_id,
                int(target_idx),
                int(donor_idx),
                Path(path),
                progress,
            ),
            ready,
        )

    def _create_play(self) -> None:
        book = self._selected_book()
        linked = self._selected_linked_play()
        if book is None or linked is None:
            return
        donor_idx = linked.play.index

        def ready(_value: object) -> None:
            self.progress_label.setText(f"Created play from {linked.play.name} — new index {len(book.plays)}")
            self._refresh_after_task = True

        self._run(
            lambda progress: self.host.create_play(book.asset_id, int(donor_idx), progress),
            ready,
        )

    def _export_selected(self) -> None:
        book = self._selected_book()
        if book is None:
            return
        selected, _filter = QFileDialog.getSaveFileName(
            self,
            "Export exact raw PLAY resource",
            str(Path.home() / suggested_playbook_filename(book)),
            "Raw PLAY resource (*.bin);;All files (*)",
        )
        if not selected:
            return
        destination = Path(selected)

        def ready(value: object) -> None:
            self.progress_label.setText(f"Exported {Path(value).name}")

        self._run(
            lambda progress: self.host.export_playbook(
                book.asset_id, destination, progress
            ),
            ready,
        )

    def _run(
        self,
        operation: Callable[[ProgressSink], object],
        ready: Callable[[object], None],
    ) -> None:
        if self._busy:
            return
        self._busy = True
        self.progress_bar.setRange(0, 0)
        self.progress_bar.show()
        self._refresh_controls()
        task = _Task(operation)
        self._tasks.add(task)
        task.signals.result.connect(ready)
        task.signals.progress.connect(self._progress)
        task.signals.error.connect(self.error_raised.emit)

        def finished() -> None:
            self._tasks.discard(task)
            self._busy = False
            self.progress_bar.hide()
            self._refresh_controls()
            if self._refresh_after_task:
                self._refresh_after_task = False
                QTimer.singleShot(0, self.refresh)

        task.signals.finished.connect(finished)
        self._pool.start(task)

    def _progress(self, stage: str, completed: int, total: int) -> None:
        self.progress_label.setText(stage or "Working…")
        if total > 0:
            self.progress_bar.setRange(0, total)
            self.progress_bar.setValue(max(0, min(total, completed)))
        else:
            self.progress_bar.setRange(0, 0)

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QWidget#playbooksPanel {
                background: #111823; color: #eaf0f8;
                font-family: Inter, "Noto Sans", sans-serif; font-size: 13px;
            }
            QLabel#playTitle { color: #fff; font-size: 27px; font-weight: 750; }
            QLabel#playDetailTitle { color: #fff; font-size: 20px; font-weight: 700; }
            QLabel#playMuted, QLabel#playFieldLabel { color: #91a0b5; }
            QLabel#playCountPill {
                color: #7fc8ff; background: #162d46; border: 1px solid #28597d;
                border-radius: 10px; padding: 5px 10px; font-weight: 650;
            }
            QLabel#playBoundary {
                color: #ffd08a; background: #352818; border: 1px solid #79562a;
                border-radius: 9px; padding: 10px 13px; font-weight: 700;
            }
            QLabel#playRawNote {
                color: #cbd6e4; background: #172130; border: 1px solid #28384d;
                border-radius: 8px; padding: 8px;
            }
            QFrame#playCard {
                background: #151f2c; border: 1px solid #28384d; border-radius: 10px;
            }
            QLineEdit, QComboBox {
                color: #eaf0f8; background: #151f2c; border: 1px solid #34475e;
                border-radius: 7px; padding: 7px 9px; min-height: 20px;
            }
            QLineEdit:focus, QComboBox:focus { border-color: #4f9cf9; }
            QTableWidget {
                color: #dce5f1; background: #151f2c;
                alternate-background-color: #182433; border: 1px solid #28384d;
                gridline-color: #26364a; selection-background-color: #244f76;
                selection-color: #fff;
            }
            QHeaderView::section {
                color: #91a0b5; background: #121b27; border: none;
                border-bottom: 1px solid #304158; padding: 7px; font-weight: 650;
            }
            QTabWidget::pane {
                background: #151f2c; border: 1px solid #28384d; border-radius: 8px;
            }
            QTabBar::tab {
                color: #9dabc0; background: #121b27; border: 1px solid #28384d;
                padding: 8px 14px;
            }
            QTabBar::tab:selected { color: #fff; background: #1b2b3e; }
            QTextBrowser#playFindings {
                color: #d9e3ef; background: #151f2c; border: none; padding: 14px;
            }
            QPushButton {
                color: #dce8f7; background: #233247; border: 1px solid #3a506b;
                border-radius: 7px; padding: 8px 13px; font-weight: 600;
            }
            QPushButton:hover { background: #2a3d56; }
            QPushButton:disabled { color: #68778b; background: #192330; }
            QPushButton#playPrimaryButton {
                color: #07131d; background: #62b9f2; border-color: #62b9f2;
            }
            QProgressBar {
                background: #172130; border: 1px solid #304158;
                border-radius: 4px; height: 7px;
            }
            QProgressBar::chunk { background: #62b9f2; border-radius: 3px; }
            """
        )


__all__ = [
    "BrokenPlayAnnotation",
    "FormationPlayRow",
    "PLAY_EDITOR_FINDINGS_HTML",
    "PLAY_EDITOR_FINDINGS_PLAIN_TEXT",
    "PlaybookActionState",
    "PlaybookBrowserResult",
    "PlaybooksPanel",
    "PlaybooksPanelHost",
    "broken_play_annotations",
    "book_has_community_flags",
    "filter_playbooks",
    "format_formation_package_map_line",
    "format_play_name_with_warnings",
    "formation_play_rows",
    "playbook_action_state",
    "playbook_search_text",
    "suggested_playbook_filename",
]
