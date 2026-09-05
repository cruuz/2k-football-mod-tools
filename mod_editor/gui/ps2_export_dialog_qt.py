"""Modal window that exports edited Xbox uniform art as a PCSX2 texture pack.

The window owns presentation and gating only.  Reading the project, loading the
shipped manifest, deciding what each edited target maps to and writing the pack
all stay behind :mod:`mod_editor.core.ps2_export_service`, which is Qt-free and
independently verified by ``tools/nfl2k5_ps2_replacement_pack_verify.py``.

Three boundaries are deliberate.

*The hard rule is the service's, not this window's.*  An unedited target is
never written, and that is enforced structurally in ``plan_export``: an
``ExportProject`` carries only edited targets, so there is no path from a
catalog or a disc into an output file.  This dialog therefore never filters,
never re-derives a name and never invents a target.  It shows what the plan
says and calls ``run_export`` on it.

*It refuses nothing the service refuses.*  In particular the destination folder
must not already exist -- the service publishes with a no-clobber primitive and
raises with its own wording.  Pre-empting that check here would give the user
two different sentences for one condition and would drift the moment the
service's rule changed, so the chooser accepts what the user picks and the
service's message is surfaced verbatim.

*No retail pixels ever reach this window.*  The plan carries the user's own
replacement PNGs and nothing else; the table shows names, statuses and counts.
There is no preview of disc art, no byte editing and no disc writing.

The manifest may be absent from a given build (it is produced by a separate
work package).  That is reported as a plain sentence and leaves every control
disabled, rather than raising on construction.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Any, Callable, Optional, Tuple

from mod_editor.core import ps2_export_service as service
from mod_editor.core.errors import ValidationError
from mod_editor.core.ps2_export_service import (
    STATUS_AMBIGUOUS,
    STATUS_MAPPED,
    STATUS_UNMAPPED,
    Ps2ExportError,
)

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

BOUNDARY_NOTE = (
    "EDITED ART ONLY  •  Only the targets you have edited are written. Nothing "
    "is read from your disc and nothing is written to it; the pack is a folder "
    "of your own PNGs named the way PenguinScreen2 looks them up."
)

MISSING_MANIFEST_NOTE = (
    "The PS2 texture map is not shipped in this build, so no export can be "
    "planned here yet. Nothing was changed."
)

PROJECT_FILTER = "2K5 Mod Studio project (*.2k5mod)"

#: The two PenguinScreen2 settings a replacement pack needs before the game
#: will draw it. The manifest is the authority -- its provenance carries
#: ``requires_setting`` -- but the requirement is a fact about the emulator's
#: loader rather than about one map, so these stand in when a manifest predates
#: the key. Getting this wrong is silent: the game simply draws the retail art.
DEFAULT_REQUIRED_SETTINGS = (
    "ClassicTextureNames=true",
    "LoadTextureReplacements=true",
)

STATUS_LABELS = {
    STATUS_MAPPED: "Will export",
    STATUS_UNMAPPED: "Skipped - not in the map",
    STATUS_AMBIGUOUS: "Skipped - ambiguous",
}

_INVALID_COLOUR = "#ff7b84"
_MATCH_COLOUR = "#39d98a"
_WARN_COLOUR = "#e8c46a"
_TABLE_BASE = "#101827"
_TABLE_ALTERNATE = "#17243a"
_TABLE_TEXT = "#edf3fc"


# --------------------------------------------------------------------------
# Qt-free view model: everything below is testable without a QApplication.
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Ps2ExportActionState:
    """Headless control gating shared by the dialog and its tests."""

    can_choose_project: bool
    can_export: bool
    can_verify: bool


def ps2_export_action_state(
    *,
    plan_ready: bool,
    busy: bool,
    mapped_count: int,
    exported: bool,
) -> Ps2ExportActionState:
    """Compute button gating without consulting any widget.

    Export needs a plan -- which means a manifest loaded and a project read --
    and at least one *mapped* target: a plan whose every entry is skipped would
    publish a folder holding nothing but a receipt, which is a confusing way to
    say "none of your edits are in the map yet".
    """

    return Ps2ExportActionState(
        can_choose_project=not busy,
        can_export=bool(plan_ready and not busy and mapped_count > 0),
        can_verify=bool(exported and not busy),
    )


def status_label(value: str) -> str:
    """Human wording for a plan entry's status; unknown values are refused."""

    try:
        return STATUS_LABELS[value]
    except KeyError as exc:
        raise ValidationError(
            "An export status is mapped, unmapped or ambiguous."
        ) from exc


def suggested_pack_name(project_source: str) -> str:
    """Default folder name for the output chooser.

    The service refuses a destination that already exists, so the suggestion is
    only ever a starting point; it is derived from the project so two exports
    from two projects do not land on the same name by default.
    """

    stem = Path(str(project_source or "").strip()).stem.strip()
    if not stem:
        stem = "nfl2k5-ps2"
    return f"{stem}-pcsx2-pack"


def plan_summary_text(mapped: int, skipped: int, files: int) -> str:
    """The line under the table, in the user's terms rather than the plan's."""

    if not mapped and not skipped:
        return "This project has no edited texture targets to export."
    if not mapped:
        return (
            f"None of the {skipped} edited target"
            f"{'' if skipped == 1 else 's'} is in the PS2 texture map yet, so "
            "there is nothing to export."
        )
    return (
        f"{mapped} of {mapped + skipped} edited target"
        f"{'' if mapped + skipped == 1 else 's'} will write {files} PCSX2 "
        f"file{'' if files == 1 else 's'}."
    )


def live_session_hint(project: Any, planned_entries: int) -> str:
    """Why a live session can plan nothing, when that is what has happened.

    A saved ``.2k5mod`` carries each edit's PNG, so a project read from one is
    complete.  A live session publishes *which* ids are modified but, in this
    build, no accessor the exporter is allowed to use for the staged bytes --
    the exporter deliberately reads only what a session publishes rather than
    reaching into its private edit map.  So a session with edits plans zero
    targets, and saying "no edited targets" would be untrue.  Returns "" when
    the situation does not apply.
    """

    if planned_entries or project is None:
        return ""
    if isinstance(project, (str, Path)):
        return ""
    modified = getattr(project, "modified_asset_ids", None)
    if modified is None:
        return ""
    try:
        count = len(list(modified))
    except TypeError:  # pragma: no cover - defensive
        return ""
    if not count:
        return ""
    return (
        f"The open session reports {count} edited item"
        f"{'' if count == 1 else 's'}, but it does not hand staged replacement "
        "images to the exporter in this build. Save the project as a .2k5mod "
        "and choose it here to export those edits."
    )


def required_settings(provenance: Any) -> Tuple[str, ...]:
    """The PenguinScreen2 settings this pack needs, from the manifest.

    ``requires_setting`` is carried in the manifest's provenance.  Where it sits
    inside that block is the manifest's business -- top level today, plausibly
    under ``emulator`` tomorrow -- so this looks one level down as well as at
    the top, accepts a mapping, a sequence or a single string, and falls back to
    :data:`DEFAULT_REQUIRED_SETTINGS` when the key is absent.  It never returns
    an empty tuple: a pack shown without its settings looks like it works and
    then silently draws retail art.
    """

    found = _find_requires_setting(provenance)
    values = _normalise_settings(found)
    return values or DEFAULT_REQUIRED_SETTINGS


def _find_requires_setting(provenance: Any) -> Any:
    if not isinstance(provenance, dict):
        return None
    if "requires_setting" in provenance:
        return provenance["requires_setting"]
    for value in provenance.values():
        if isinstance(value, dict) and "requires_setting" in value:
            return value["requires_setting"]
    return None


def _normalise_settings(found: Any) -> Tuple[str, ...]:
    if found is None:
        return ()
    if isinstance(found, str):
        return (found.strip(),) if found.strip() else ()
    if isinstance(found, dict):
        rows = []
        for key in sorted(found):
            value = found[key]
            if isinstance(value, bool):
                value = "true" if value else "false"
            rows.append(f"{key}={value}")
        return tuple(rows)
    if isinstance(found, Sequence):
        rows = []
        for entry in found:
            if isinstance(entry, dict):
                rows.extend(_normalise_settings(entry))
            elif str(entry).strip():
                rows.append(str(entry).strip())
        return tuple(rows)
    return (str(found),)


def penguinscreen2_instructions(
    destination: Path, provenance: Any = None
) -> str:
    """What to do with the folder that was just written.

    The settings line is not decoration.  PenguinScreen2 only looks for these
    filenames when the classic naming convention is on, and only loads them when
    replacement loading is on; with either off the game draws the retail art and
    the user concludes the export failed.
    """

    settings = required_settings(provenance)
    body = [
        f"1. Copy the textures folder from\n     {destination}\n"
        "   into PenguinScreen2's texture directory, keeping the "
        f"{'/'.join(service.REPLACEMENTS_DIR)} path intact.",
        "2. Turn on these PenguinScreen2 settings before booting:",
    ]
    body.extend(f"     • {row}" for row in settings)
    body.append(
        "   Without both of them the game draws the retail art and the pack "
        "looks like it did nothing."
    )
    body.append(
        f"3. Boot your own {service.SERIAL} disc and go to a moment where the "
        "art you edited is on screen."
    )
    return "\n".join(body)


def receipt_summary_text(receipt: Any) -> str:
    """The headline over the instructions, counting what actually landed."""

    files = tuple(getattr(receipt, "files", ()) or ())
    skipped = tuple(getattr(receipt, "skipped", ()) or ())
    resampled = sum(1 for row in files if getattr(row, "resampled_from", None))
    targets = len({getattr(row, "source_target", "") for row in files})
    parts = [
        f"Wrote {len(files)} PCSX2 file{'' if len(files) == 1 else 's'} "
        f"from {targets} edited target{'' if targets == 1 else 's'}."
    ]
    if resampled:
        parts.append(
            f"{resampled} were resampled to the PS2 aspect (PCSX2 scales any "
            "replacement size, so only the aspect matters)."
        )
    if skipped:
        parts.append(
            f"{len(skipped)} target{'' if len(skipped) == 1 else 's'} "
            "skipped; see the table for why."
        )
    return " ".join(parts)


def verdict_text(report: Any) -> str:
    """One line for the independent verifier's report."""

    if not isinstance(report, dict):
        return "The verifier returned nothing to report."
    result = str(report.get("result", "")) or "UNKNOWN"
    checked = report.get("files_checked", 0)
    line = f"Verifier: {result} • {checked} file(s) re-checked from the bytes."
    reason = report.get("downgrade_reason")
    if reason:
        line += f" {reason}"
    return line


# --------------------------------------------------------------------------
# Widgets
# --------------------------------------------------------------------------

from PyQt5.QtCore import (  # noqa: E402
    QObject,
    QRunnable,
    Qt,
    QThreadPool,
    pyqtSignal,
)
from PyQt5.QtGui import QColor  # noqa: E402
from PyQt5.QtWidgets import (  # noqa: E402
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

PYQT5_AVAILABLE = True


class _TaskSignals(QObject):
    """Cross-thread channel for one background operation."""

    result = pyqtSignal(object)
    error = pyqtSignal(str)
    stage = pyqtSignal(str)
    finished = pyqtSignal()


class _Task(QRunnable):
    """Run one service call off the Qt thread.

    Writing a pack resamples PNGs and fsyncs every file, which on a large edit
    set is seconds of work; inside a click handler that marks the window
    unresponsive.  ``signals`` is constructed on the Qt thread, so every
    emission from :meth:`run` is delivered as a queued call.
    """

    def __init__(self, operation: Callable[[Callable[[str], None]], object]) -> None:
        super().__init__()
        self.operation = operation
        self.signals = _TaskSignals()
        self.setAutoDelete(False)

    def run(self) -> None:
        try:
            result = self.operation(self.signals.stage.emit)
        except BaseException as exc:
            self.signals.error.emit(str(exc).strip() or exc.__class__.__name__)
        else:
            self.signals.result.emit(result)
        finally:
            self.signals.finished.emit()


class Ps2ExportDialog(QDialog):
    """Plan, write and verify one PCSX2 replacement pack.

    ``project`` is whatever the caller has: a live studio session or facade, a
    ``.2k5mod`` path, an already-built ``ExportProject``, or ``None`` to start
    with the project chooser.  Coercion is the service's ``load_project``, so
    this window has no opinion about which one it was given.
    """

    def __init__(
        self,
        project: Any = None,
        *,
        manifest: Any = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._project_source = project
        self._manifest_source = manifest
        self._plan = None
        self._receipt = None
        self._busy = False
        self._busy_verb = ""
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(1)
        self._task: Optional[_Task] = None
        self._task_outcome: object = None
        self._task_error: Optional[str] = None
        self._task_done: Optional[Callable[[object], None]] = None
        self._task_title = ""
        self._task_note = ""
        #: Set only when the project came from a ``.2k5mod`` on disk. The
        #: verifier's strongest check -- no exported file names an unedited
        #: target -- needs the archive as a third input, and a live session has
        #: no path to give it.
        self._project_path: Optional[Path] = (
            Path(project) if isinstance(project, (str, Path)) else None
        )

        self.setObjectName("ps2ExportDialog")
        self.setWindowTitle("Export PS2 Replacement Pack")
        self.setModal(True)
        self.setMinimumSize(840, 560)
        self.resize(1040, 680)
        self._build_ui()
        self._apply_style()
        self._connect()
        self._replan()

    # -- construction --------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(12)

        header = QHBoxLayout()
        titles = QVBoxLayout()
        title = QLabel("Export PS2 Replacement Pack")
        title.setObjectName("panelTitle")
        subtitle = QLabel(
            "Write the uniform art you have edited as a folder of PCSX2 "
            "texture replacements for the PlayStation 2 release. Your Xbox "
            "project and your discs are not changed."
        )
        subtitle.setObjectName("mutedLabel")
        subtitle.setWordWrap(True)
        titles.addWidget(title)
        titles.addWidget(subtitle)
        header.addLayout(titles, 1)

        self.project_button = QPushButton("Choose Project…")
        self.project_button.setAccessibleName("Choose a saved project to export")
        self.project_button.setAccessibleDescription(
            "Pick a .2k5mod project file. Only the texture edits it records are "
            "exported."
        )
        header.addWidget(self.project_button)
        root.addLayout(header)

        boundary = QLabel(BOUNDARY_NOTE)
        boundary.setObjectName("exportBoundary")
        boundary.setWordWrap(True)
        root.addWidget(boundary)

        self.info_label = QLabel("Planning the export…")
        self.info_label.setObjectName("exportInfoCard")
        self.info_label.setWordWrap(True)
        self.info_label.setTextFormat(Qt.PlainText)
        root.addWidget(self.info_label)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(
            ("Target", "Status", "Why", "PCSX2 files")
        )
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setAccessibleName("What this export will write")
        self.table.setAccessibleDescription(
            "One row per edited target: its id, whether it will be exported, "
            "the reason it will not be, and how many PCSX2 files it writes."
        )
        head = self.table.horizontalHeader()
        head.setSectionResizeMode(QHeaderView.ResizeToContents)
        head.setSectionResizeMode(2, QHeaderView.Stretch)
        root.addWidget(self.table, 1)

        self.receipt_label = QLabel("")
        self.receipt_label.setObjectName("exportReceiptCard")
        self.receipt_label.setWordWrap(True)
        self.receipt_label.setTextFormat(Qt.PlainText)
        self.receipt_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.receipt_label.hide()
        root.addWidget(self.receipt_label)

        footer = QHBoxLayout()
        footer.setSpacing(12)
        self.status_label = QLabel("")
        self.status_label.setObjectName("statusLabel")
        self.status_label.setTextFormat(Qt.PlainText)
        self.status_label.setWordWrap(True)
        footer.addWidget(self.status_label, 1)
        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("ps2ProgressBar")
        # Indeterminate: the service reports what it is doing, not a fraction.
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedWidth(180)
        self.progress_bar.setAccessibleName("Operation in progress")
        self.progress_bar.hide()
        footer.addWidget(self.progress_bar, 0)
        root.addLayout(footer)

        self.button_box = QDialogButtonBox(QDialogButtonBox.Close)
        self.export_button = self.button_box.addButton(
            "Export Pack…", QDialogButtonBox.ActionRole
        )
        self.export_button.setAccessibleName("Write the replacement pack")
        self.export_button.setAccessibleDescription(
            "Choose a new folder and write one PNG per mapped PCSX2 name, plus "
            "a receipt and the texture map."
        )
        self.verify_button = self.button_box.addButton(
            "Verify Pack", QDialogButtonBox.ActionRole
        )
        self.verify_button.setAccessibleName("Independently verify the pack")
        self.verify_button.setAccessibleDescription(
            "Re-check the exported folder from its bytes with the standalone "
            "verifier, which shares no code with the exporter."
        )
        root.addWidget(self.button_box)

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QDialog#ps2ExportDialog QLabel#panelTitle {
                font-size: 17px; font-weight: 600;
            }
            QDialog#ps2ExportDialog QLabel#mutedLabel { color: #91a0b5; }
            QDialog#ps2ExportDialog QLabel#exportBoundary {
                background: #10261b; border: 1px solid #1f5a3a;
                border-radius: 6px; padding: 9px; color: #39d98a;
            }
            QDialog#ps2ExportDialog QLabel#exportInfoCard,
            QDialog#ps2ExportDialog QLabel#exportReceiptCard {
                background: #101827; border: 1px solid #22304a;
                border-radius: 6px; padding: 9px;
            }
            QDialog#ps2ExportDialog QTableWidget {
                background: %s; alternate-background-color: %s; color: %s;
            }
            """
            % (_TABLE_BASE, _TABLE_ALTERNATE, _TABLE_TEXT)
        )

    def _connect(self) -> None:
        self.project_button.clicked.connect(self._choose_project)
        self.export_button.clicked.connect(self._export)
        self.verify_button.clicked.connect(self._verify)
        self.button_box.rejected.connect(self.reject)

    # -- background operations -----------------------------------------

    def _start(
        self,
        verb: str,
        title: str,
        operation: Callable[[Callable[[str], None]], object],
        done: Callable[[object], None],
        failure_note: str = "Nothing was written.",
    ) -> None:
        """Hand one service call to the pool and settle when it lands."""

        self._busy = True
        self._busy_verb = verb
        self._task_title = title
        self._task_note = failure_note
        self._task_done = done
        self._task_outcome = None
        self._task_error = None
        self.status_label.setStyleSheet("")
        self._status(f"{verb}…")
        self.progress_bar.show()
        self._refresh_controls()
        task = _Task(operation)
        self._task = task
        task.signals.stage.connect(self._status)
        task.signals.result.connect(self._task_succeeded)
        task.signals.error.connect(self._task_failed)
        task.signals.finished.connect(self._task_finished)
        self._pool.start(task)

    def _task_succeeded(self, result: object) -> None:
        self._task_outcome = result

    def _task_failed(self, message: str) -> None:
        self._task_error = message or f"{self._busy_verb} failed."

    def _task_finished(self) -> None:
        """Clear the busy state first, then report -- never a modal over a spinner."""

        outcome, error, done, title, note = (
            self._task_outcome, self._task_error, self._task_done,
            self._task_title, self._task_note,
        )
        self._task = None
        self._task_outcome = None
        self._task_error = None
        self._task_done = None
        self._busy = False
        self.progress_bar.hide()
        if error is not None:
            self._refresh_controls()
            self.status_label.setStyleSheet(f"color: {_INVALID_COLOUR};")
            self._status(error)
            QMessageBox.warning(self, title, f"{error}\n\n{note}")
            return
        if done is not None:
            done(outcome)
        self._refresh_controls()

    # -- planning ------------------------------------------------------

    def _replan(self) -> None:
        """Rebuild the plan for the current project, in the foreground.

        Planning reads the project archive and the manifest and measures each
        PNG's IHDR; it decodes nothing and writes nothing, so it is fast enough
        to run inline and lets the window open already showing its table.
        """

        self._plan = None
        self._receipt = None
        self.receipt_label.hide()
        if self._project_source is None:
            self.table.setRowCount(0)
            self.info_label.setText(
                "Choose a saved .2k5mod project to see what it would export."
            )
            self.status_label.setStyleSheet("")
            self._status("No project is open.")
            self._refresh_controls()
            return
        try:
            self._plan = service.plan_export(
                self._project_source, self._manifest_source
            )
        except Ps2ExportError as exc:
            self.table.setRowCount(0)
            self.info_label.setText(self._plan_failure_text(exc))
            self.status_label.setStyleSheet(f"color: {_INVALID_COLOUR};")
            self._status(str(exc).strip())
            self._refresh_controls()
            return
        self._fill_table()
        self._refresh_controls()

    def _plan_failure_text(self, exc: BaseException) -> str:
        """Say why nothing can be planned, in the terms the cause deserves."""

        message = str(exc).strip()
        if not self._manifest_ready():
            return f"{MISSING_MANIFEST_NOTE}\n\n{message}"
        return f"This project could not be planned for export.\n\n{message}"

    def _manifest_ready(self) -> bool:
        """Whether this build ships the texture map at all.

        Asked of the filesystem rather than of a failed exception, because the
        answer changes the wording for every other failure too: a build with no
        map cannot plan anything, and saying so once is kinder than reporting a
        missing file per project.
        """

        source = self._manifest_source
        if source is None:
            return service.DEFAULT_MANIFEST_PATH.is_file()
        if isinstance(source, (str, Path)):
            return Path(source).is_file()
        return True

    def _fill_table(self) -> None:
        plan = self._plan
        entries = tuple(getattr(plan, "entries", ()) or ())
        self.table.setRowCount(len(entries))
        for row, entry in enumerate(entries):
            count = len(entry.pcsx2_pngs) if entry.is_mapped else 0
            cells = (
                entry.target_id,
                status_label(entry.status),
                entry.reason,
                str(count),
            )
            for column, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setToolTip(text)
                if column == 1:
                    item.setForeground(QColor(
                        _MATCH_COLOUR if entry.is_mapped else _WARN_COLOUR
                    ))
                self.table.setItem(row, column, item)
        mapped = len(getattr(plan, "mapped", ()))
        skipped = len(getattr(plan, "skipped", ()))
        summary = plan_summary_text(mapped, skipped, getattr(plan, "file_count", 0))
        hint = live_session_hint(self._project_source, len(entries))
        source = getattr(plan, "project_source", "") or "the open project"
        lines = [f"Project: {source}", hint or summary]
        self.info_label.setText("\n".join(lines))
        self.status_label.setStyleSheet("")
        self._status(hint or summary)

    # -- choosing a project --------------------------------------------

    def _choose_project(self) -> None:
        if self._busy:
            return
        selected, _filter = QFileDialog.getOpenFileName(
            self, "Choose a 2K5 Mod Studio project", str(Path.home()),
            PROJECT_FILTER,
        )
        if not selected:
            return
        self.set_project(Path(selected))

    def set_project(self, project: Any) -> None:
        """Adopt a new project and re-plan. Public so a caller can preload one."""

        self._project_source = project
        self._project_path = (
            Path(project) if isinstance(project, (str, Path)) else None
        )
        self._replan()

    # -- exporting -----------------------------------------------------

    def _export(self) -> None:
        if self._busy or self._plan is None:
            return
        suggested = suggested_pack_name(getattr(self._plan, "project_source", ""))
        # A folder that does not exist yet cannot be picked with the directory
        # chooser, and the service refuses one that does, so the destination is
        # named rather than browsed to.
        selected, _filter = QFileDialog.getSaveFileName(
            self, "Name a new folder for the replacement pack",
            str(Path.home() / suggested), "",
            options=QFileDialog.DontConfirmOverwrite,
        )
        if not selected:
            return
        destination = Path(selected)
        plan = self._plan
        self._start(
            "Writing the replacement pack",
            "The replacement pack could not be written",
            lambda _stage: service.run_export(plan, destination),
            self._exported,
        )

    def _exported(self, receipt: Any) -> None:
        self._receipt = receipt
        provenance = getattr(receipt, "provenance", None)
        self.receipt_label.setText(
            receipt_summary_text(receipt)
            + "\n\n"
            + penguinscreen2_instructions(getattr(receipt, "path", Path("")),
                                          provenance)
        )
        self.receipt_label.show()
        self.status_label.setStyleSheet(f"color: {_MATCH_COLOUR};")
        self._status(
            f"Wrote {len(getattr(receipt, 'files', ()))} file(s) to "
            f"{getattr(receipt, 'path', '')}"
        )
        self._offer_verification()

    # -- verifying -----------------------------------------------------

    def _offer_verification(self) -> None:
        """Ask before running the verifier; it re-reads every file it wrote."""

        answer = QMessageBox.question(
            self,
            "Verify the pack?",
            "Check the folder that was just written with the independent "
            "verifier? It shares no code with the exporter and re-derives "
            "every filename, digest and provenance field from the bytes.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if answer == QMessageBox.Yes:
            self._verify()

    def _verify(self) -> None:
        if self._busy or self._receipt is None:
            return
        pack = Path(getattr(self._receipt, "path", ""))
        project = self._project_path
        self._start(
            "Verifying the pack",
            "The pack did not verify",
            lambda _stage: self._run_verifier(pack, project),
            self._verified,
            failure_note=(
                "The pack is still on disk exactly as it was written; only the "
                "check failed. Do not use it until the reason above is resolved."
            ),
        )

    @staticmethod
    def _run_verifier(pack: Path, project: Optional[Path]) -> object:
        """Call the standalone verifier in this process, on the pool thread.

        Imported here rather than at module scope so a build without the tool
        fails at the click, with a message, instead of at import time.  The
        pack ships its own manifest copy, so the verifier is left to find it
        there -- passing ours would let a bad copy in the pack go unnoticed.
        """

        import nfl2k5_ps2_replacement_pack_verify as verifier

        return verifier.verify(pack, None, project)

    def _verified(self, report: object) -> None:
        line = verdict_text(report)
        passed = isinstance(report, dict) and report.get("result") == "PASS"
        self.status_label.setStyleSheet(
            f"color: {_MATCH_COLOUR if passed else _WARN_COLOUR};"
        )
        self._status(line)
        if not passed:
            QMessageBox.information(self, "Verifier result", line)

    # -- shared --------------------------------------------------------

    def _refresh_controls(self) -> None:
        plan = self._plan
        state = ps2_export_action_state(
            plan_ready=plan is not None,
            busy=self._busy,
            mapped_count=len(getattr(plan, "mapped", ())) if plan else 0,
            exported=self._receipt is not None,
        )
        self.project_button.setEnabled(state.can_choose_project)
        self.export_button.setEnabled(state.can_export)
        self.verify_button.setEnabled(state.can_verify)
        self.table.setEnabled(not self._busy)

    def done(self, result: int) -> None:
        """Refuse to close while a write or a verification is in flight."""

        if self._busy:
            self._status(
                f"{self._busy_verb} is still running. It will finish in a moment."
            )
            return
        super().done(result)

    def _status(self, message: str) -> None:
        self.status_label.setText(message)
        self.status_label.setToolTip(message)


__all__ = [
    "BOUNDARY_NOTE",
    "DEFAULT_REQUIRED_SETTINGS",
    "MISSING_MANIFEST_NOTE",
    "PROJECT_FILTER",
    "PYQT5_AVAILABLE",
    "STATUS_LABELS",
    "Ps2ExportActionState",
    "Ps2ExportDialog",
    "live_session_hint",
    "penguinscreen2_instructions",
    "plan_summary_text",
    "ps2_export_action_state",
    "receipt_summary_text",
    "required_settings",
    "status_label",
    "suggested_pack_name",
    "verdict_text",
]
