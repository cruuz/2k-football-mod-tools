"""Saves-page action: import a PS3 APF 2K8 roster save as a raw Xbox 360 ``Roster.ROS``."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from PyQt5.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .ps3_roster_convert import (
    ConversionReceipt,
    PLATFORM_PS3,
    PS3RosterConvertError,
    RUNTIME_STATUS,
    detect_platform,
    find_roster_member,
    inspect_structure,
    read_source,
    write_conversion,
)


Progress = Callable[[str, int, int], None]
TaskRunner = Callable[
    [str, Callable[[Progress], object], Callable[[object], None] | None, bool], bool
]

XENIA_PLACEMENT = (
    "Xenia keeps game-created saves as folders under its content root "
    "(content/54540807/00000001/<save name>/Roster.ROS). Drop this raw Roster.ROS "
    "over the Roster.ROS of a save the game itself created, then load that roster "
    "in-game. Loading a converted roster is UNWITNESSED so far."
)


class Ps3RosterImportPanel(QWidget):
    """Import PS3 roster... : convert one PS3 USERDATA (or its ZIP) and receipt the result."""

    def __init__(self, run_task: TaskRunner):
        super().__init__()
        self.run_task = run_task
        self.source: Path | None = None
        self.member: str | None = None
        self.summary: dict[str, object] | None = None
        self.last_receipt: ConversionReceipt | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)
        heading = QLabel("Import PS3 roster")
        heading.setObjectName("panelTitle")
        note = QLabel(
            "Convert a PS3 All-Pro Football 2K8 roster save (the decrypted USERDATA, "
            "or the ZIP that holds a BLUS30049-ROS folder) into the raw Xbox 360 "
            "Roster.ROS layout the studio's save editors read: every player, team, "
            "playbook label and user playbook bank is kept; palette colours are "
            "rotated to the Xbox byte order, serialised runtime words are rewritten "
            "the way Xbox saves carry them, and editor-damaged text (misaligned "
            "strings, stale references) is realigned or blanked. The output is a raw "
            "payload plus a JSON receipt; the source is never modified. Nobody has "
            "loaded a converted roster in Xenia yet: UNWITNESSED."
        )
        note.setObjectName("mutedLabel")
        note.setWordWrap(True)
        layout.addWidget(heading)
        layout.addWidget(note)

        source_row = QHBoxLayout()
        self.choose_button = QPushButton("Choose PS3 roster…")
        self.source_label = QLabel("No PS3 roster chosen")
        self.source_label.setObjectName("mutedLabel")
        self.source_label.setWordWrap(True)
        source_row.addWidget(self.choose_button)
        source_row.addWidget(self.source_label, 1)
        layout.addLayout(source_row)

        self.summary_label = QLabel("")
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)

        action_row = QHBoxLayout()
        self.convert_button = QPushButton("Import PS3 roster…")
        self.convert_button.setEnabled(False)
        action_row.addWidget(self.convert_button)
        action_row.addStretch(1)
        layout.addLayout(action_row)
        layout.addStretch(1)

        self.choose_button.clicked.connect(self._choose_source)
        self.convert_button.clicked.connect(self._choose_output)

    # -- source -----------------------------------------------------------

    def _choose_source(self) -> None:
        selected, _filter = QFileDialog.getOpenFileName(
            self,
            "Choose a PS3 APF 2K8 roster save",
            str(Path.home()),
            "PS3 roster save (USERDATA *.zip);;All files (*)",
        )
        if selected:
            self.load_path(Path(selected))

    def load_path(self, path: Path) -> None:
        self.run_task(
            "Inspecting PS3 roster",
            lambda progress: self._inspect_operation(path, progress),
            self._loaded,
            True,
        )

    @staticmethod
    def _inspect_operation(path: Path, progress: Progress) -> dict[str, object]:
        progress("Reading the PS3 roster read-only", 0, 2)
        member = find_roster_member(path) if path.suffix.casefold() == ".zip" else None
        data = read_source(path, member)
        structure = inspect_structure(data)
        platform = detect_platform(data, structure)
        odd = sum(1 for reference in structure.references if reference.target % 2)
        progress("Structure inventory ready", 2, 2)
        return {
            "path": path,
            "member": member,
            "size": len(data),
            "platform": platform,
            "players": structure.tables[0].count,
            "teams": structure.tables[4].count,
            "string_references": len(structure.references),
            "odd_references": odd,
            "stale_references": sum(1 for reference in structure.references if reference.target in structure.interior),
        }

    def _loaded(self, result: object) -> None:
        if not isinstance(result, dict):
            raise PS3RosterConvertError("PS3 roster inspection returned an invalid summary")
        self.summary = result
        self.source = Path(str(result["path"]))
        self.member = result["member"] if isinstance(result["member"], str) else None
        member = f" · {self.member}" if self.member else ""
        self.source_label.setText(f"{self.source.name}{member} · {int(result['size']):,} bytes")
        platform = str(result["platform"])
        if platform == PLATFORM_PS3:
            verdict = "PS3 layout detected (palette colours RGBA)."
        elif platform == "xbox360":
            verdict = "Already an Xbox 360 layout roster; nothing to import."
        else:
            verdict = "Platform could not be told from the palette colours; import refused."
        self.summary_label.setText(
            f"{verdict} {int(result['players'])} players, {int(result['teams'])} teams, "
            f"{int(result['string_references']):,} text references of which "
            f"{int(result['odd_references']):,} are misaligned and "
            f"{int(result['stale_references']):,} are stale."
        )
        self.convert_button.setEnabled(platform == PLATFORM_PS3)

    # -- conversion -------------------------------------------------------

    def _choose_output(self) -> None:
        if self.source is None:
            return
        suggested = self.source.with_name(f"{self.source.stem}-xbox360.ROS")
        selected, _filter = QFileDialog.getSaveFileName(
            self,
            "Write the converted raw Xbox 360 roster",
            str(suggested),
            "Raw APF roster payload (*.ROS);;All files (*)",
        )
        if selected:
            self.convert_to(Path(selected))

    def convert_to(self, destination: Path) -> None:
        source, member = self.source, self.member
        if source is None:
            return
        self.run_task(
            "Importing PS3 roster",
            lambda progress: self._convert_operation(source, member, destination, progress),
            self._converted,
            True,
        )

    @staticmethod
    def _convert_operation(source: Path, member: str | None, destination: Path, progress: Progress) -> ConversionReceipt:
        progress("Converting and re-parsing with the strict readers", 0, 2)
        receipt = write_conversion(source, destination, member=member)
        progress("Raw Xbox 360 roster and receipt written", 2, 2)
        return receipt

    def _converted(self, result: object) -> None:
        if not isinstance(result, ConversionReceipt):
            raise PS3RosterConvertError("PS3 roster conversion returned an invalid receipt")
        self.last_receipt = result
        QMessageBox.information(self, "PS3 roster imported", self.receipt_text(result))

    @staticmethod
    def receipt_text(result: ConversionReceipt) -> str:
        counts = result.counts
        return (
            f"Saved: {result.output}\nReceipt: {result.receipt_path}\n\n"
            f"{int(counts['players'])} players, {int(counts['teams'])} teams "
            f"({int(counts['team_memberships'])} roster slots), {int(counts['playbook_labels'])} playbook labels "
            f"and every user playbook bank kept. {int(counts['odd_runs'])} misaligned string runs realigned "
            f"({int(counts['odd_run_bytes'])} bytes), {int(counts['references_repointed']):,} text references repointed "
            f"({int(counts['interior_references']):,} stale, {int(counts['empty_references_canonicalised']):,} empty), "
            f"{int(counts['palette_colours_rotated'])} palette colours rotated, "
            f"{int(counts['root_runtime_fields_rewritten']) + int(counts['runtime_block_words_rewritten']) + int(counts['bank_runtime_words_rewritten'])} "
            f"runtime words rewritten; {result.changed_byte_count:,} bytes changed. Source unchanged.\n\n"
            f"{XENIA_PLACEMENT}\n\nStatus: {RUNTIME_STATUS}"
        )


__all__ = ["Ps3RosterImportPanel", "XENIA_PLACEMENT"]
