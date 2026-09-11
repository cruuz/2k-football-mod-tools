"""Saves-page action: import a PS3 APF 2K8 roster save as a raw Xbox 360 ``Roster.ROS``."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from PyQt5.QtWidgets import (
    QFileDialog,
    QCheckBox,
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
        self.appearance_baseline: Path | None = None

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

        self.apply_appearance = QCheckBox("Also apply team appearance (0 teams)")
        self.apply_appearance.setChecked(False)
        self.apply_appearance.setToolTip("Carry both uniform selector banks and team palettes. Custom texture files need a separate PS3 texture import.")
        self.keep_appearance_button = QPushButton("Keep appearance from Xbox roster…")
        self.appearance_note = QLabel("Review team appearance: tick the option to use the PS3 uniforms, or choose an Xbox roster to keep its appearance.")
        self.appearance_note.setWordWrap(True)
        layout.addWidget(self.apply_appearance)
        layout.addWidget(self.keep_appearance_button)
        layout.addWidget(self.appearance_note)
        self.keep_appearance_button.clicked.connect(self._choose_appearance_baseline)
        self.apply_appearance.toggled.connect(self._review_appearance)

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
            "PS3 roster save (USERDATA *.ROS *.ros *.zip);;All files (*)",
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
        self.apply_appearance.setText(f"Also apply team appearance ({int(result['teams'])} teams)")
        self.apply_appearance.setChecked(False)
        self._review_appearance()

    def _choose_appearance_baseline(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(self, "Xbox roster appearance to retain", str(Path.home()),
                                                 "Raw Xbox roster (*.ROS *.ros);;All files (*)")
        if selected:
            self.set_appearance_baseline(Path(selected))

    def set_appearance_baseline(self, path: Path) -> None:
        # Validate at review time and again in the worker before any output write.
        from .ps3_roster_convert import team_appearance
        data = read_source(path)
        if detect_platform(data) != "xbox360":
            raise PS3RosterConvertError("Choose a raw Xbox 360 roster for retained appearance")
        team_appearance(data)
        self.appearance_baseline = path
        self.apply_appearance.setChecked(False)
        self.appearance_note.setText(f"Unticked: retain team appearance from {path.name}. Ticked: apply PS3 appearance. Custom texture files are imported separately.")
        self._review_appearance()

    def _review_appearance(self) -> None:
        ready = self.summary is not None and self.summary["platform"] == PLATFORM_PS3
        self.convert_button.setEnabled(ready and (self.apply_appearance.isChecked() or self.appearance_baseline is not None))

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
        apply_appearance = self.apply_appearance.isChecked()
        baseline = self.appearance_baseline
        if not apply_appearance and baseline is None:
            raise PS3RosterConvertError("Review team appearance before importing")
        self.run_task(
            "Importing PS3 roster",
            lambda progress: self._convert_operation(source, member, destination, progress, apply_appearance, baseline),
            self._converted,
            True,
        )

    @staticmethod
    def _convert_operation(source: Path, member: str | None, destination: Path, progress: Progress, apply_appearance: bool = True, baseline: Path | None = None) -> ConversionReceipt:
        progress("Converting and re-parsing with the strict readers", 0, 2)
        receipt = write_conversion(source, destination, member=member,
                                   apply_team_appearance=apply_appearance, xbox_appearance=baseline)
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
            f"Team appearance: {counts.get('appearance_teams', counts['teams'])} teams, "
            f"{'applied from PS3' if counts.get('appearance_applied_from_ps3', True) else 'retained from Xbox roster'}. "
            "Both selector banks reparsed; each team's before/after selectors are in the receipt. "
            "Custom texture payloads require a separate texture import.\n\n"
            f"{XENIA_PLACEMENT}\n\nStatus: {RUNTIME_STATUS}"
        )


__all__ = ["Ps3RosterImportPanel", "XENIA_PLACEMENT"]
