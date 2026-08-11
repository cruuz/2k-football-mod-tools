"""Edit the stock CPU playbooks APF 2K8 ships.

Reassigning which book a team calls from -- all the community's editor can do,
and all this product could do before -- is a coarse control: the 36 offensive
and 33 defensive book records in a roster save are *labels* that resolve to
seven offensive and four defensive real books, so the swap frequently changes
nothing at all.

This panel edits those real books.  Each is an on-disc ``SPLB`` resource of
exactly 32,288 bytes holding a 176-record array; a populated record names a
MASTER formation and lists the plays the CPU may call from it, as big-endian
u16 entries whose low ten bits are the MASTER play index.  Ticking a play
rewrites only that record's entry list.

Everything else is preserved and independently re-derived before publication:
the record trailer, every other record, the two tail regions whose meaning is
not established, and every other byte of the volume.  The four tagged slots per
formation have an unproved meaning, so removing one is refused rather than
guessed, and no claim is made about in-game CPU behaviour.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from mod_editor.core import apf2k8_splb_writer as splb
from mod_editor.core.errors import ValidationError


TaskRunner = Callable[[str, object, object, bool], None]

BOUNDARY = (
    "This edits the stock CPU playbooks themselves — the SPLB resources the "
    "game ships, one per book. Only the entry list of the selected formation's "
    "record is rewritten; the record trailer, every other record and every "
    "other byte stay exact, and an independent verifier re-derives every "
    "changed byte before anything is written. The four tagged slots per "
    "formation have an unproved meaning, so removing one is refused rather "
    "than guessed. In-game CPU behaviour is NOT proved."
)


class ApfPlaybookMembershipPanel(QFrame):
    """Pick a stock book, pick a formation, tick plays in and out."""

    modifiedChanged = pyqtSignal()

    def __init__(self, facade, run_task: TaskRunner):
        super().__init__()
        self.facade = facade
        self.run_task = run_task
        self.setObjectName("panel")
        self._book: splb.SplbBook | None = None
        self._plays: list[str] = []
        self._formations: dict[int, str] = {}
        # record index -> {play index: wanted membership}
        self._staged: dict[int, dict[int, bool]] = {}
        self._loading = False

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(9)

        heading = QHBoxLayout()
        title = QLabel("Stock CPU playbooks")
        title.setObjectName("panelTitle")
        self.status = QLabel("Not loaded")
        self.status.setObjectName("statusBadge")
        heading.addWidget(title)
        heading.addStretch(1)
        heading.addWidget(self.status)
        root.addLayout(heading)

        blurb = QLabel(
            "Reassigning a team's book usually changes nothing: the 36 offensive "
            "and 33 defensive book names in a save are labels over seven "
            "offensive and four defensive real books. These are those books."
        )
        blurb.setObjectName("mutedLabel")
        blurb.setWordWrap(True)
        root.addWidget(blurb)

        book_row = QHBoxLayout()
        book_row.setSpacing(8)
        book_row.addWidget(QLabel("Playbook:"))
        self.book_picker = QComboBox()
        self.book_picker.setObjectName("comboField")
        self.book_picker.setAccessibleName("Stock CPU playbook")
        self.book_picker.setToolTip(
            "The fifteen stock playbook resources the game ships. Eleven carry "
            "a name; four are unnamed and are shown by their archive entry."
        )
        for outer, name in sorted(splb.STOCK_BOOKS.items()):
            label = name or f"(unnamed book, entry {outer})"
            self.book_picker.addItem(label, outer)
        self.book_picker.currentIndexChanged.connect(lambda _i: self._load_book())
        book_row.addWidget(self.book_picker, 1)
        root.addLayout(book_row)

        columns = QHBoxLayout()
        columns.setSpacing(14)

        left = QVBoxLayout()
        left.setSpacing(6)
        self.formation_list = QListWidget()
        self.formation_list.setObjectName("assetList")
        self.formation_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.formation_list.currentItemChanged.connect(
            lambda _current, _previous: self._refresh_plays()
        )
        left.addWidget(QLabel("Formations this book uses"))
        left.addWidget(self.formation_list, 1)
        columns.addLayout(left, 2)

        right = QVBoxLayout()
        right.setSpacing(6)
        self.play_search = QLineEdit()
        self.play_search.setPlaceholderText("Search plays…")
        self.play_search.setClearButtonEnabled(True)
        self.play_search.setProperty("studioSearch", True)
        self.play_search.setAccessibleName("Search APF plays")
        self.play_search.textChanged.connect(lambda _text: self._refresh_plays())
        self.play_list = QListWidget()
        self.play_list.setObjectName("assetList")
        self.play_list.setToolTip(
            "Ticked plays are the ones the CPU may call from this formation in "
            "this book. Tick to add, untick to remove."
        )
        self.play_list.itemChanged.connect(self._play_toggled)
        self.play_header = QLabel("Plays")
        right.addWidget(self.play_header)
        right.addWidget(self.play_search)
        right.addWidget(self.play_list, 3)
        columns.addLayout(right, 3)
        root.addLayout(columns, 1)

        note = QLabel(BOUNDARY)
        note.setObjectName("findingText")
        note.setWordWrap(True)
        root.addWidget(note)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.revert_button = QPushButton("Revert changes")
        self.revert_button.setObjectName("dangerQuietButton")
        self.build_button = QPushButton("Build copied 0A (playbook)…")
        self.build_button.setObjectName("primaryButton")
        self.revert_button.clicked.connect(self._revert)
        self.build_button.clicked.connect(self._build)
        actions.addStretch(1)
        actions.addWidget(self.revert_button)
        actions.addWidget(self.build_button)
        root.addLayout(actions)

        self.set_context()

    # ---------------------------------------------------------------- context

    def _index_0a(self) -> Path | None:
        source = getattr(self.facade, "source", None)
        value = getattr(source, "index_0a", None) if source is not None else None
        return Path(value) if value is not None else None

    def set_context(self) -> None:
        if not bool(getattr(self.facade, "source_ready", False)):
            self._book = None
            self._staged = {}
            self.formation_list.clear()
            self.play_list.clear()
            self.status.setText("Not loaded")
            self._refresh_actions()
            return
        self._load_book()

    def _load_book(self) -> None:
        index_0a = self._index_0a()
        if index_0a is None or not bool(getattr(self.facade, "source_ready", False)):
            return
        outer = self.book_picker.currentData()
        if outer is None:
            return
        self._staged = {}

        def operation(progress: Callable[[str, int, int], None]) -> dict:
            import playbook_inventory  # type: ignore

            progress("Reading the stock playbook", 0, 2)
            book = splb.read_book(index_0a, int(outer))
            progress("Reading MASTER play names", 1, 2)
            master = playbook_inventory.parse_apf(index_0a, 64 * 1024 * 1024)[0]
            progress("Playbook ready", 2, 2)
            return {
                "book": book,
                "plays": [str(p["name"]) for p in master["plays"]],
                "formations": {
                    int(f["index"]): str(f["name"]) for f in master["formations"]
                },
            }

        def done(result: object) -> None:
            payload = result  # type: ignore[assignment]
            self._book = payload["book"]  # type: ignore[index]
            self._plays = payload["plays"]  # type: ignore[index]
            self._formations = payload["formations"]  # type: ignore[index]
            used = [r for r in self._book.records if r.populated]
            self.status.setText(
                f"{self._book.name or 'unnamed'} · {len(used)} formations"
            )
            self._refresh_formations()
            self._refresh_actions()

        self.run_task("Opening the stock playbook", operation, done, False)

    # ------------------------------------------------------------------- view

    def _refresh_formations(self) -> None:
        selected = self._selected_record_index()
        self.formation_list.blockSignals(True)
        self.formation_list.clear()
        row_to_select = -1
        if self._book is not None:
            for record in self._book.records:
                if not record.populated:
                    continue
                name = self._formations.get(record.formation_index, "?")
                count = len(self._wanted_plays(record.record_index))
                label = f"{name}  ·  {count} plays"
                staged = self._staged.get(record.record_index) or {}
                if staged:
                    label += f"   ✎ {len(staged)} changed"
                item = QListWidgetItem(label)
                item.setData(Qt.UserRole, record.record_index)
                self.formation_list.addItem(item)
                if record.record_index == selected:
                    row_to_select = self.formation_list.count() - 1
        self.formation_list.blockSignals(False)
        if row_to_select < 0 and self.formation_list.count():
            row_to_select = 0
        if row_to_select >= 0:
            self.formation_list.setCurrentRow(row_to_select)
        else:
            self._refresh_plays()

    def _selected_record_index(self) -> int | None:
        item = self.formation_list.currentItem()
        return int(item.data(Qt.UserRole)) if item is not None else None

    def _record(self, record_index: int) -> splb.SplbRecord | None:
        if self._book is None:
            return None
        return self._book.records[record_index]

    def _wanted_plays(self, record_index: int) -> set[int]:
        record = self._record(record_index)
        if record is None:
            return set()
        base = {entry.play_index for entry in record.entries}
        for play_index, wanted in (self._staged.get(record_index) or {}).items():
            if wanted:
                base.add(play_index)
            else:
                base.discard(play_index)
        return base

    def _refresh_plays(self) -> None:
        self._loading = True
        try:
            self.play_list.clear()
            record_index = self._selected_record_index()
            record = self._record(record_index) if record_index is not None else None
            if record is None or not self._plays:
                self.play_header.setText("Plays")
                return
            tagged = {e.play_index: e.y for e in record.entries if e.tagged}
            wanted = self._wanted_plays(record.record_index)
            needle = self.play_search.text().strip().casefold()
            for play_index, name in enumerate(self._plays):
                if needle and needle not in name.casefold():
                    continue
                item = QListWidgetItem(
                    f"{name}   [tagged slot {tagged[play_index]}]"
                    if play_index in tagged
                    else name
                )
                item.setData(Qt.UserRole, play_index)
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(
                    Qt.Checked if play_index in wanted else Qt.Unchecked
                )
                if play_index in tagged:
                    item.setToolTip(
                        "This is one of the four tagged slots for this formation. "
                        "Their meaning is unproved, so removing one is refused."
                    )
                self.play_list.addItem(item)
            self.play_header.setText(
                f"Plays the CPU may call from "
                f"{self._formations.get(record.formation_index, '?')} — "
                f"{len(wanted)} of {len(self._plays)}"
            )
        finally:
            self._loading = False
        self._refresh_actions()

    def _play_toggled(self, item: QListWidgetItem) -> None:
        if self._loading:
            return
        record_index = self._selected_record_index()
        record = self._record(record_index) if record_index is not None else None
        if record is None:
            return
        play_index = int(item.data(Qt.UserRole))
        wanted = item.checkState() == Qt.Checked
        tagged = {e.play_index: e.y for e in record.entries if e.tagged}
        if not wanted and play_index in tagged:
            self._loading = True
            item.setCheckState(Qt.Checked)
            self._loading = False
            QMessageBox.information(
                self,
                "That slot is tagged",
                f"{self._plays[play_index]} occupies tagged slot "
                f"{tagged[play_index]} for this formation. Every populated "
                "record carries exactly one slot 1 and at most one each of 0, "
                "2 and 3; what those four denote is not established, so this "
                "build refuses to remove one rather than guess what it breaks.",
            )
            return
        base = {e.play_index for e in record.entries}
        staged = self._staged.setdefault(record.record_index, {})
        if wanted == (play_index in base):
            staged.pop(play_index, None)
            if not staged:
                self._staged.pop(record.record_index, None)
        else:
            staged[play_index] = wanted
        self._refresh_formations()
        self._refresh_actions()
        self.modifiedChanged.emit()

    # ---------------------------------------------------------------- actions

    def staged_changes(self) -> tuple[splb.MembershipChange, ...]:
        if self._book is None:
            return ()
        out: list[splb.MembershipChange] = []
        for record_index, plays in sorted(self._staged.items()):
            for play_index, wanted in sorted(plays.items()):
                out.append(
                    splb.MembershipChange(
                        self._book.outer_index, record_index, play_index, wanted
                    )
                )
        return tuple(out)

    def _refresh_actions(self) -> None:
        staged = self.staged_changes()
        # Never silent-gray: both stay clickable and explain.
        self.revert_button.setEnabled(True)
        self.build_button.setEnabled(True)
        if not bool(getattr(self.facade, "source_ready", False)):
            block = "Load your APF game first, then pick a playbook."
        elif self._book is None:
            block = "Choose a stock playbook first."
        elif not staged:
            block = "Tick or untick plays for a formation first. Nothing is staged yet."
        else:
            block = ""
        self.build_button.setProperty("disableReason", block)
        self.build_button.setToolTip(
            block
            or f"Write {len(staged)} playbook change"
            f"{'s' if len(staged) != 1 else ''} into a copied 0A. Your source is "
            "never opened for writing."
        )
        revert_block = "" if staged else "There are no staged playbook changes."
        self.revert_button.setProperty("disableReason", revert_block)
        self.revert_button.setToolTip(
            revert_block or f"Discard {len(staged)} staged change(s)."
        )

    def _revert(self) -> None:
        reason = str(self.revert_button.property("disableReason") or "").strip()
        if reason:
            QMessageBox.information(self, "Nothing to revert", reason)
            return
        self._staged = {}
        self._refresh_formations()
        self._refresh_plays()
        self._refresh_actions()
        self.modifiedChanged.emit()

    def _build(self) -> None:
        reason = str(self.build_button.property("disableReason") or "").strip()
        if reason:
            QMessageBox.information(self, "Cannot build the playbook yet", reason)
            return
        index_0a = self._index_0a()
        if index_0a is None:
            return
        directory = QFileDialog.getExistingDirectory(
            self, "Choose an empty folder for the modded volume", str(Path.home())
        )
        if not directory:
            return
        out_root = Path(directory)
        if any(out_root.iterdir()):
            QMessageBox.information(
                self,
                "Choose an empty folder",
                "The build writes a complete copied volume and never overwrites "
                "anything. Choose an empty folder and try again.",
            )
            return
        changes = self.staged_changes()

        def operation(progress: Callable[[str, int, int], None]) -> dict:
            progress("Compiling the stock playbook", 0, 2)
            entry = splb.build_book_patch(index_0a, changes)
            progress("Writing the copied volume", 1, 2)
            written = _publish_copied_volume(index_0a, out_root, entry)
            progress("Modded playbook ready", 2, 2)
            return {"path": written, "report": entry.report}

        def done(result: object) -> None:
            payload = result  # type: ignore[assignment]
            report = payload["report"]  # type: ignore[index]
            verification = report.get("verification", {})
            QMessageBox.information(
                self,
                "Modded playbook built",
                f"Wrote:\n{payload['path']}\n\n"  # type: ignore[index]
                f"{len(report['changes'])} change"
                f"{'s' if len(report['changes']) != 1 else ''} to "
                f"{report['book_name'] or 'an unnamed book'} · "
                f"{verification.get('changed_byte_count', 0)} byte(s) differ from "
                "your source.\n\n" + BOUNDARY,
            )

        self.run_task("Building the modded playbook", operation, done, True)


def _publish_copied_volume(index_path: Path, out_root: Path, entry) -> Path:
    """Copy the user's volume and replace only the one rebuilt entry."""

    from mod_editor.apf_studio.backend import ensure_tools_importable

    ensure_tools_importable()
    import apf_logo_patch  # type: ignore
    import apf_outer  # type: ignore

    source_root = index_path.parent
    for sibling in source_root.iterdir():
        if sibling.name == index_path.name or not sibling.is_file():
            continue
        target = out_root / sibling.name
        if not target.exists():
            target.symlink_to(sibling.resolve())
    archive = apf_outer.parse_archive(index_path)
    outer_entry = archive.entries[entry.outer_index]
    destination = out_root / index_path.name
    apf_logo_patch._write_copied_volume(
        index_path, destination, outer_entry, entry.entry_bytes
    )
    return destination


__all__ = ["ApfPlaybookMembershipPanel", "BOUNDARY"]
