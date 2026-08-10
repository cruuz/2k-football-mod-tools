"""Add and remove plays inside an APF 2K8 formation.

Until now the only playbook edit either this product or the community's editor
offered was reassigning which stock book a team calls from -- and the 36
offensive and 33 defensive book records in a roster save are labels that
collapse to a handful of distinct types, so that swap frequently changes
nothing at all.

This panel edits the level below it.  APF's MASTER ``PLAY`` resource stores one
fixed 74-byte bitmap per formation over the book's 586 plays; ticking a play
here sets or clears one bit.  Nothing moves, no count changes, and the
resource's byte extent is identical, so the whole edit is provable by byte diff
-- which is why this is offerable when freehand route authoring still is not.

The boundary is stated on the panel and not softened: this changes the book the
game selects plays from.  Whether the CPU's play-calling reads the same table
is untested, and the CPU book *types* are named only inside a roster save.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QAbstractItemView,
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

from mod_editor.core import apf2k8_playbook_membership_writer as membership
from mod_editor.core.apf2k8_playbook_route_writer import read_master_play_body
from mod_editor.core.errors import ValidationError


TaskRunner = Callable[[str, object, object, bool], None]

BOUNDARY = (
    "This edits MASTER PLAY: which plays each formation offers. It is a "
    "bitmap edit inside a fixed allocation — no play, route, name or count is "
    "rewritten, and an independent verifier re-derives every changed byte. "
    "Whether the CPU's play-calling reads this table is NOT proved."
)


class ApfPlaybookMembershipPanel(QFrame):
    """Tick plays in and out of one formation, then build a copied 0A."""

    modifiedChanged = pyqtSignal()

    def __init__(self, facade, run_task: TaskRunner):
        super().__init__()
        self.facade = facade
        self.run_task = run_task
        self.setObjectName("panel")
        self._formations: list[dict] = []
        self._plays: list[dict] = []
        # formation index -> {play index: wanted membership}
        self._staged: dict[int, dict[int, bool]] = {}
        self._loading = False

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(9)

        heading = QHBoxLayout()
        title = QLabel("Fine-tune a formation's plays")
        title.setObjectName("panelTitle")
        self.status = QLabel("Not loaded")
        self.status.setObjectName("statusBadge")
        heading.addWidget(title)
        heading.addStretch(1)
        heading.addWidget(self.status)
        root.addLayout(heading)

        blurb = QLabel(
            "Reassigning a team's book usually changes nothing: the 36 offensive "
            "and 33 defensive book names in a save are labels over a handful of "
            "real types. This edits the plays themselves."
        )
        blurb.setObjectName("mutedLabel")
        blurb.setWordWrap(True)
        root.addWidget(blurb)

        columns = QHBoxLayout()
        columns.setSpacing(14)

        left = QVBoxLayout()
        left.setSpacing(6)
        self.formation_search = QLineEdit()
        self.formation_search.setPlaceholderText("Search formations…")
        self.formation_search.setClearButtonEnabled(True)
        self.formation_search.setProperty("studioSearch", True)
        self.formation_search.setAccessibleName("Search APF formations")
        self.formation_search.textChanged.connect(lambda _text: self._refresh_formations())
        self.formation_list = QListWidget()
        self.formation_list.setObjectName("assetList")
        self.formation_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.formation_list.currentItemChanged.connect(
            lambda _current, _previous: self._refresh_plays()
        )
        left.addWidget(QLabel("Formations"))
        left.addWidget(self.formation_search)
        left.addWidget(self.formation_list, 1)
        columns.addLayout(left, 2)

        right = QVBoxLayout()
        right.setSpacing(6)
        self.play_search = QLineEdit()
        self.play_search.setPlaceholderText("Search plays…")
        self.play_search.setClearButtonEnabled(True)
        self.play_search.setAccessibleName("Search APF plays")
        self.play_search.textChanged.connect(lambda _text: self._refresh_plays())
        self.play_list = QListWidget()
        self.play_list.setObjectName("assetList")
        self.play_list.setToolTip(
            "Ticked plays belong to the selected formation. Tick to add, untick "
            "to remove."
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

    def set_context(self) -> None:
        ready = bool(getattr(self.facade, "source_ready", False))
        if not ready:
            self._formations = []
            self._plays = []
            self._staged = {}
            self.formation_list.clear()
            self.play_list.clear()
            self.status.setText("Not loaded")
            self._refresh_actions()
            return
        source = getattr(self.facade, "source", None)
        index_0a = getattr(source, "index_0a", None) if source is not None else None
        if index_0a is None:
            return

        def operation(progress: Callable[[str, int, int], None]) -> dict:
            progress("Reading MASTER PLAY", 0, 1)
            body = read_master_play_body(Path(index_0a))
            parsed = membership._parse(body)
            progress("MASTER PLAY ready", 1, 1)
            return {
                "formations": list(parsed["formations"]),
                "plays": list(parsed["plays"]),
            }

        def done(result: object) -> None:
            payload = result  # type: ignore[assignment]
            self._formations = list(payload["formations"])  # type: ignore[index]
            self._plays = list(payload["plays"])  # type: ignore[index]
            self.status.setText(
                f"{len(self._formations)} formations · {len(self._plays)} plays"
            )
            self._refresh_formations()
            self._refresh_actions()

        self.run_task("Opening the APF playbook", operation, done, False)

    # ------------------------------------------------------------------- view

    def _refresh_formations(self) -> None:
        needle = self.formation_search.text().strip().casefold()
        selected = self._selected_formation_index()
        self.formation_list.blockSignals(True)
        self.formation_list.clear()
        row_to_select = -1
        for formation in self._formations:
            name = str(formation["name"])
            if needle and needle not in name.casefold():
                continue
            index = int(formation["index"])
            edits = self._staged.get(index) or {}
            changed = sum(
                1
                for play_index, wanted in edits.items()
                if wanted != (play_index in set(formation["play_membership_indices"]))
            )
            label = f"{name}  ·  {formation['play_membership_count']} plays"
            if changed:
                label += f"   ✎ {changed} changed"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, index)
            self.formation_list.addItem(item)
            if index == selected:
                row_to_select = self.formation_list.count() - 1
        self.formation_list.blockSignals(False)
        if row_to_select < 0 and self.formation_list.count():
            row_to_select = 0
        if row_to_select >= 0:
            self.formation_list.setCurrentRow(row_to_select)
        else:
            self._refresh_plays()

    def _selected_formation_index(self) -> int | None:
        item = self.formation_list.currentItem()
        return int(item.data(Qt.UserRole)) if item is not None else None

    def _wanted(self, formation_index: int, play_index: int) -> bool:
        formation = self._formations[formation_index]
        base = play_index in set(formation["play_membership_indices"])
        return self._staged.get(formation_index, {}).get(play_index, base)

    def _refresh_plays(self) -> None:
        self._loading = True
        try:
            self.play_list.clear()
            index = self._selected_formation_index()
            if index is None or not self._plays:
                self.play_header.setText("Plays")
                return
            formation = self._formations[index]
            needle = self.play_search.text().strip().casefold()
            members = 0
            for play in self._plays:
                play_index = int(play["index"])
                wanted = self._wanted(index, play_index)
                members += int(wanted)
                name = str(play["name"])
                if needle and needle not in name.casefold():
                    continue
                item = QListWidgetItem(name)
                item.setData(Qt.UserRole, play_index)
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Checked if wanted else Qt.Unchecked)
                self.play_list.addItem(item)
            self.play_header.setText(
                f"Plays in {formation['name']} — {members} of {len(self._plays)}"
            )
        finally:
            self._loading = False
        self._refresh_actions()

    def _play_toggled(self, item: QListWidgetItem) -> None:
        if self._loading:
            return
        formation_index = self._selected_formation_index()
        if formation_index is None:
            return
        play_index = int(item.data(Qt.UserRole))
        wanted = item.checkState() == Qt.Checked
        base = play_index in set(
            self._formations[formation_index]["play_membership_indices"]
        )
        edits = self._staged.setdefault(formation_index, {})
        if wanted == base:
            edits.pop(play_index, None)
            if not edits:
                self._staged.pop(formation_index, None)
        else:
            edits[play_index] = wanted
        self._refresh_formations()
        self._refresh_actions()
        self.modifiedChanged.emit()

    # ---------------------------------------------------------------- actions

    def staged_edits(self) -> tuple[membership.MembershipEdit, ...]:
        edits: list[membership.MembershipEdit] = []
        for formation_index, plays in sorted(self._staged.items()):
            for play_index, wanted in sorted(plays.items()):
                edits.append(
                    membership.MembershipEdit(formation_index, play_index, wanted)
                )
        return tuple(edits)

    def _refresh_actions(self) -> None:
        ready = bool(getattr(self.facade, "source_ready", False))
        staged = self.staged_edits()
        # Never silent-gray: both actions stay clickable and explain.
        self.revert_button.setEnabled(True)
        self.build_button.setEnabled(True)
        if not ready:
            block = "Load your APF game first, then pick a formation."
        elif not staged:
            block = (
                "Tick or untick plays for a formation first. Nothing is staged yet."
            )
        else:
            block = ""
        self.build_button.setProperty("disableReason", block)
        self.build_button.setToolTip(
            block
            or f"Write {len(staged)} membership change"
            f"{'s' if len(staged) != 1 else ''} into a copied 0A. Your source is "
            "never opened for writing."
        )
        revert_block = "" if staged else "There are no staged playbook changes."
        self.revert_button.setProperty("disableReason", revert_block)
        self.revert_button.setToolTip(
            revert_block or f"Discard {len(staged)} staged membership change(s)."
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
        source = getattr(self.facade, "source", None)
        index_0a = getattr(source, "index_0a", None) if source is not None else None
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
        edits = self.staged_edits()

        def operation(progress: Callable[[str, int, int], None]) -> dict:
            progress("Compiling playbook membership", 0, 2)
            entry = membership.build_membership_patch(Path(index_0a), edits)
            progress("Writing the copied volume", 1, 2)
            written = _publish_copied_volume(Path(index_0a), out_root, entry)
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
                f"{report['changed_bit_count']} membership change"
                f"{'s' if report['changed_bit_count'] != 1 else ''} · "
                f"{verification.get('changed_byte_count', 0)} byte(s) differ from "
                "your source.\n\n" + BOUNDARY,
            )

        self.run_task("Building the modded playbook", operation, done, True)


def _publish_copied_volume(index_path: Path, out_root: Path, entry) -> Path:
    """Copy the user's volume and replace only the one rebuilt entry.

    Reuses the crest writer's copy primitive, which never opens the source for
    writing and byte-checks the copy before the replacement lands.
    """

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
