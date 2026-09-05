"""Modal PS2 Disc Studio for ESPN NFL 2K5: one window over the six on-disc writers.

The window owns presentation and gating only.  Opening the ISO, building each
lane's catalogue from it, checking an edit, composing and dry-running a recipe,
writing a NEW image and running the independent verifiers all stay behind
:class:`Ps2DiscStudioHost`, which
:class:`mod_editor.core.ps2_disc_studio_service.Ps2DiscStudioService`
implements.  The six lane tabs live in :mod:`ps2_disc_studio_tabs_qt`.

Three boundaries are deliberate, the same three the PS2 save, disc-inventory
and export windows keep.

*A PS2 disc image is the user's own file* and has nothing to do with the Xbox
game image the main window may have open, so this is a self-contained dialog
off the File menu, not a page in the project workspace.

*It refuses nothing the service refuses, and re-words nothing.*  Every inline
budget sentence, every plan refusal and every build refusal is the lane's or
the service's own text, surfaced verbatim: one condition, one sentence.

*The source is never written and nothing here claims a screen.*  The window
says so in its boundary note, its Build page and its receipt; every lane is
offline-proved only, and the caveats each tab shows come from the lane's
registry row.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Protocol, Sequence, runtime_checkable

from mod_editor.core.errors import ValidationError
from mod_editor.core.ps2_disc_studio_lanes import LANE_ORDER, lanes_in_order

BOUNDARY_NOTE = (
    "NEW IMAGE  •  Your disc image is opened read-only and never changed. Only the edits you "
    "stage are written, into a new file that is created only after every check passes and is "
    "verified by each lane's independent checker. Nothing built here has been seen or heard in an "
    "emulator yet."
)

UNSUPPORTED_DISC_NOTE = (
    "This is not the SLUS-20919 disc the six writers were proved on. You can look at what is "
    "here, but nothing will be planned or built from it."
)

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
class Ps2DiscStudioActionState:
    """Headless control gating shared by the window and its tests."""

    can_open: bool
    can_build_catalogue: bool
    can_edit: bool
    can_check: bool
    can_build: bool
    can_cancel: bool
    can_open_folder: bool


def ps2_disc_studio_action_state(
    *, disc_open: bool, supported: bool, busy: bool, catalogue_built: bool,
    staged_count: int, plans_ready: bool, built: bool,
) -> Ps2DiscStudioActionState:
    """Compute gating without consulting any widget.

    Build needs every staged lane to have a clean plan (``plans_ready``): the
    dry run is where the patchers' refusals surface, so a build is never
    offered before it has been done for the recipe as it now stands.
    """

    live = disc_open and not busy
    return Ps2DiscStudioActionState(
        can_open=not busy,
        can_build_catalogue=live,
        can_edit=bool(live and catalogue_built),
        can_check=bool(live and supported and staged_count > 0),
        can_build=bool(live and supported and staged_count > 0 and plans_ready),
        can_cancel=busy,
        can_open_folder=bool(built and not busy),
    )


def suggested_destination(image_name: str) -> str:
    """Default file name for the destination chooser: never the source's name."""

    stem = Path(str(image_name).strip()).stem or "nfl2k5-ps2"
    return f"{stem}-modded.iso"


def queue_summary_text(edits_by_lane: Dict[str, int], plans: Dict[str, Any], stale: Sequence[str]) -> str:
    """The line over the Build page's queue, in the user's terms."""

    staged = {lane_id: count for lane_id, count in edits_by_lane.items() if count}
    if not staged:
        return "Nothing is staged yet. Add an edit on one of the lane tabs."
    total = sum(staged.values())
    lanes = len(staged)
    unplanned = [lane_id for lane_id in staged if lane_id not in plans or lane_id in stale]
    text = f"{total} edit{'' if total == 1 else 's'} staged across {lanes} lane{'' if lanes == 1 else 's'}"
    if unplanned:
        text += (f"; {len(unplanned)} lane{'' if len(unplanned) == 1 else 's'} not checked yet — "
                 "choose Check everything before building.")
    else:
        text += "; every lane checked clean, ready to build."
    return text


def catalogue_status_text(lane_title: str, built: bool, summary: str, seconds: Optional[float]) -> str:
    if not built:
        return f"{lane_title}: catalogue not built for this disc yet."
    took = f" (built in {seconds:.0f} s)" if seconds else ""
    return f"{lane_title}: {summary}{took}"


def receipt_text(receipt: Any) -> str:
    """The receipt card: per step what changed, what the verifier said, how long it took."""

    steps = tuple(getattr(receipt, "steps", ()) or ())
    lines = [str(getattr(receipt, "message", ""))]
    for step in steps:
        seconds = getattr(step, "seconds", {}) or {}
        total = sum(float(value) for value in seconds.values())
        lines.append(
            f"Step {getattr(step, 'index', '?')} · {getattr(step, 'lane_id', '?')}: "
            f"{getattr(step, 'plan_summary', '')}\n"
            f"   {getattr(step, 'verdict_summary', '')}\n"
            f"   {total:.0f} s (write {seconds.get('write', 0):.0f} s, verify {seconds.get('verify', 0):.0f} s)"
        )
    path = getattr(receipt, "receipt_path", None)
    if path:
        lines.append(f"Receipt: {path}")
    digest = getattr(receipt, "destination_sha256", "")
    if digest:
        lines.append(f"New image SHA-256: {digest}")
    return "\n".join(line for line in lines if line)


@runtime_checkable
class Ps2DiscStudioHost(Protocol):
    """The complete backend boundary consumed by the window and its tabs."""

    OPEN_FILTER: str
    WAV_FILTER: str
    SAVE_FILTER: str

    @property
    def is_open(self) -> bool: ...

    @property
    def source_path(self) -> Optional[Path]: ...

    def identity(self) -> Any: ...

    def open(self, path: Path, progress: Optional[Callable[[str], None]] = None) -> Any: ...

    def close(self) -> None: ...

    def lanes(self) -> Sequence[Any]: ...

    def lane(self, lane_id: str) -> Any: ...

    def catalogue_state(self, lane_id: str, scope: str = "default") -> Any: ...

    def catalogue(self, lane_id: str, scope: str = "default") -> dict: ...

    def build_catalogue(self, lane_id: str, scope: str = "default",
                        progress: Optional[Callable[[str], None]] = None, cancel: Any = None) -> Any: ...

    def targets(self, lane_id: str, scope: str = "default") -> Sequence[Any]: ...

    def check_edit(self, lane_id: str, target: Any, values: dict, staged: Sequence[Any] = ()) -> Optional[str]: ...

    def stage(self, lane_id: str, target: Any, values: dict, staged: Sequence[Any] = ()) -> Any: ...

    def compose(self, lane_id: str, edits: Sequence[Any], scope: str = "default") -> Sequence[Any]: ...

    def recipe_preview(self, steps: Sequence[Any]) -> str: ...

    def plan_lane(self, lane_id: str, edits: Sequence[Any], scope: str = "default",
                  progress: Optional[Callable[[str], None]] = None, cancel: Any = None) -> Any: ...

    def estimate(self, steps: int, destination: Path) -> Any: ...

    def build(self, plans: Sequence[Any], destination: Path, progress: Optional[Callable[[str], None]] = None,
              cancel: Any = None, scopes: Optional[Dict[str, str]] = None) -> Any: ...

    def last_timing(self, key: str) -> Optional[float]: ...


# --------------------------------------------------------------------------
# Widgets
# --------------------------------------------------------------------------

from PyQt5.QtCore import (  # noqa: E402
    QObject,
    QRunnable,
    Qt,
    QThreadPool,
    QTimer,
    QUrl,
    pyqtSignal,
)
from PyQt5.QtGui import QDesktopServices  # noqa: E402
from PyQt5.QtWidgets import (  # noqa: E402
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
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
    """Run one host operation off the Qt thread.

    A catalogue build decodes for seconds to minutes and a build step copies a
    4.3 GB image; inside a click handler either would mark the window
    unresponsive.  ``signals`` is constructed on the Qt thread, so every
    emission from :meth:`run` is delivered as a queued call.  ``cancel`` is the
    service's token; the Cancel button sets it and the child process the
    service is waiting on is killed.
    """

    def __init__(self, operation: Callable[[Callable[[str], None], Any], object], cancel: Any) -> None:
        super().__init__()
        self.operation = operation
        self.cancel = cancel
        self.signals = _TaskSignals()
        self.setAutoDelete(False)

    def run(self) -> None:
        try:
            result = self.operation(self.signals.stage.emit, self.cancel)
        except BaseException as exc:
            self.signals.error.emit(str(exc).strip() or exc.__class__.__name__)
        else:
            self.signals.result.emit(result)
        finally:
            self.signals.finished.emit()


def _cancel_token() -> Any:
    from mod_editor.core.ps2_disc_studio_service import CancelToken

    return CancelToken()


class BuildPage(QWidget):
    """Queue, destination, free space and time, Check everything, Build, receipt."""

    def __init__(self, window: "Ps2DiscStudioDialog") -> None:
        super().__init__(window)
        self.window = window
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        intro = QLabel(
            "Every lane with staged edits runs as one step, in a fixed order, each step writing a "
            "new image from the previous one and verifying it before the previous intermediate is "
            "deleted. Each step copies the whole image and rewrites a 1 GiB pack, so expect minutes "
            "per step and tens of minutes for a stadium step."
        )
        intro.setWordWrap(True)
        intro.setObjectName("mutedLabel")
        root.addWidget(intro)

        self.queue = QTableWidget(0, 4)
        self.queue.setHorizontalHeaderLabels(("Lane", "Edits", "Checked", "What would change"))
        self.queue.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.queue.setSelectionMode(QAbstractItemView.NoSelection)
        self.queue.setAlternatingRowColors(True)
        self.queue.verticalHeader().setVisible(False)
        self.queue.setAccessibleName("Build queue")
        self.queue.setAccessibleDescription(
            "One row per lane with staged edits: how many edits, whether its recipe has been "
            "checked against the disc, and what the check said would change."
        )
        head = self.queue.horizontalHeader()
        head.setSectionResizeMode(QHeaderView.ResizeToContents)
        head.setSectionResizeMode(3, QHeaderView.Stretch)
        root.addWidget(self.queue, 1)

        self.queue_label = QLabel("")
        self.queue_label.setWordWrap(True)
        self.queue_label.setTextFormat(Qt.PlainText)
        self.queue_label.setAccessibleName("Queue summary")
        root.addWidget(self.queue_label)

        destination_row = QHBoxLayout()
        destination_label = QLabel("New image:")
        self.destination = QLineEdit()
        self.destination.setPlaceholderText("Choose a file name that does not exist yet…")
        self.destination.setAccessibleName("Destination for the new disc image")
        self.destination.setAccessibleDescription(
            "The new ISO is created here. It must not exist yet; your original is never written."
        )
        destination_label.setBuddy(self.destination)
        self.choose_button = QPushButton("Choose…")
        self.choose_button.setAccessibleName("Choose where the new disc image is written")
        destination_row.addWidget(destination_label)
        destination_row.addWidget(self.destination, 1)
        destination_row.addWidget(self.choose_button)
        root.addLayout(destination_row)

        self.estimate_label = QLabel("")
        self.estimate_label.setWordWrap(True)
        self.estimate_label.setTextFormat(Qt.PlainText)
        self.estimate_label.setObjectName("discInfoCard")
        self.estimate_label.setAccessibleName("Free space and time expectation")
        root.addWidget(self.estimate_label)

        buttons = QHBoxLayout()
        self.check_button = QPushButton("Check everything")
        self.check_button.setAccessibleName("Check every staged recipe against the disc")
        self.check_button.setAccessibleDescription(
            "Runs each lane's own dry run. Every refusal shows here before any image exists."
        )
        self.build_button = QPushButton("Build new ISO")
        self.build_button.setAccessibleName("Build the new disc image")
        self.build_button.setAccessibleDescription(
            "Writes a new image through each lane's patcher and verifies every step. Your "
            "original disc image is not changed."
        )
        self.open_folder_button = QPushButton("Open folder")
        self.open_folder_button.setAccessibleName("Open the folder holding the new image")
        buttons.addWidget(self.check_button)
        buttons.addWidget(self.build_button)
        buttons.addWidget(self.open_folder_button)
        buttons.addStretch(1)
        root.addLayout(buttons)

        self.receipt_label = QLabel("")
        self.receipt_label.setObjectName("exportReceiptCard")
        self.receipt_label.setWordWrap(True)
        self.receipt_label.setTextFormat(Qt.PlainText)
        self.receipt_label.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
        self.receipt_label.setAccessibleName("Build receipt")
        self.receipt_label.hide()
        root.addWidget(self.receipt_label)

        self.choose_button.clicked.connect(self.window._choose_destination)
        self.check_button.clicked.connect(self.window._check_everything)
        self.build_button.clicked.connect(self.window._build)
        self.open_folder_button.clicked.connect(self.window._open_folder)
        self.destination.textChanged.connect(lambda _text: self.window._refresh_estimate())

    def refresh(self, edits_by_lane: Dict[str, int], plans: Dict[str, Any], stale: Sequence[str],
                errors: Dict[str, str]) -> None:
        rows = [(lane_id, count) for lane_id, count in edits_by_lane.items() if count]
        order = {lane_id: index for index, lane_id in enumerate(LANE_ORDER)}
        rows.sort(key=lambda item: order.get(item[0], 99))
        self.queue.setRowCount(len(rows))
        for row, (lane_id, count) in enumerate(rows):
            lane = self.window.host.lane(lane_id)
            if lane_id in errors:
                checked, what, colour = "refused", errors[lane_id], _INVALID_COLOUR
            elif lane_id in plans and lane_id not in stale:
                checked, what, colour = "yes", str(getattr(plans[lane_id], "summary", "")), _MATCH_COLOUR
            else:
                checked, what, colour = "not yet", "choose Check everything", _WARN_COLOUR
            cells = (lane.title, str(count), checked, what)
            for column, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setToolTip(text)
                if column == 2:
                    from PyQt5.QtGui import QColor

                    item.setForeground(QColor(colour))
                self.queue.setItem(row, column, item)
        self.queue_label.setText(queue_summary_text(edits_by_lane, plans, stale))


class Ps2DiscStudioDialog(QDialog):
    """Open, catalogue, edit, check, build and verify -- one PS2 disc, six lanes."""

    def __init__(
        self,
        host: Optional[Ps2DiscStudioHost] = None,
        *,
        parent: Optional[QWidget] = None,
        initial_iso: Optional[Path] = None,
    ) -> None:
        super().__init__(parent)
        if host is None:
            from mod_editor.core.ps2_disc_studio_service import Ps2DiscStudioService

            host = Ps2DiscStudioService()
        if not isinstance(host, Ps2DiscStudioHost):
            raise TypeError("PS2 Disc Studio host does not implement Ps2DiscStudioHost")
        self.host = host
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
        self._cancel: Any = None
        #: lane id -> PlanOutcome, from the last Check; ``_stale`` names lanes edited since.
        self._plans: Dict[str, Any] = {}
        self._stale: set = set()
        self._plan_errors: Dict[str, str] = {}
        self._receipt: Any = None
        self.tabs: Dict[str, Any] = {}

        self.setObjectName("ps2DiscStudioDialog")
        self.setWindowTitle("PS2 Disc Studio")
        self.setModal(True)
        self.setMinimumSize(980, 660)
        self.resize(1280, 820)
        self._build_ui()
        self._apply_style()
        self._connect()
        self._refresh_controls()
        if initial_iso is not None:
            QTimer.singleShot(0, lambda: self._open_path(Path(initial_iso)))

    # -- construction --------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(12)

        header = QHBoxLayout()
        titles = QVBoxLayout()
        title = QLabel("PS2 Disc Studio")
        title.setObjectName("panelTitle")
        subtitle = QLabel(
            "Edit text, playbooks, uniform colours, rosters, stadium positions and sounds on a "
            "copy of your ESPN NFL 2K5 PlayStation 2 disc image. Separate from the Xbox game "
            "image in the main window; a new image is written and your original is never changed."
        )
        subtitle.setObjectName("mutedLabel")
        subtitle.setWordWrap(True)
        titles.addWidget(title)
        titles.addWidget(subtitle)
        header.addLayout(titles, 1)
        self.open_button = QPushButton("Open Disc Image…")
        self.open_button.setAccessibleName("Open a PlayStation 2 disc image")
        self.open_button.setAccessibleDescription(
            "Choose your own SLUS-20919 ISO. It is opened read-only; catalogues are built from it."
        )
        header.addWidget(self.open_button)
        root.addLayout(header)

        boundary = QLabel(BOUNDARY_NOTE)
        boundary.setObjectName("discBoundary")
        boundary.setWordWrap(True)
        boundary.setAccessibleName("What this window can and cannot do")
        root.addWidget(boundary)

        self.info_label = QLabel("No disc image is open yet.")
        self.info_label.setObjectName("discInfoCard")
        self.info_label.setWordWrap(True)
        self.info_label.setTextFormat(Qt.PlainText)
        self.info_label.setAccessibleName("Disc identity and catalogue status")
        root.addWidget(self.info_label)

        self.tab_widget = QTabWidget()
        self.tab_widget.setAccessibleName("Lanes")
        self.tab_widget.setAccessibleDescription(
            "One tab per lane -- Text, Playbooks, Colours, Roster, Stadium, Audio -- and the Build page."
        )
        from mod_editor.gui.ps2_disc_studio_tabs_qt import make_lane_tab

        for lane in lanes_in_order():
            tab = make_lane_tab(self, lane)
            self.tabs[lane.id] = tab
            self.tab_widget.addTab(tab, lane.title)
        self.build_page = BuildPage(self)
        self.tab_widget.addTab(self.build_page, "Build")
        root.addWidget(self.tab_widget, 1)

        footer = QHBoxLayout()
        footer.setSpacing(12)
        self.status_label = QLabel("Open a PS2 disc image to begin.")
        self.status_label.setObjectName("statusLabel")
        self.status_label.setTextFormat(Qt.PlainText)
        self.status_label.setWordWrap(True)
        self.status_label.setAccessibleName("Current operation status")
        footer.addWidget(self.status_label, 1)
        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("ps2ProgressBar")
        self.progress_bar.setRange(0, 0)   # indeterminate: the service reports stages, not a fraction
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedWidth(180)
        self.progress_bar.setAccessibleName("Operation in progress")
        self.progress_bar.hide()
        footer.addWidget(self.progress_bar, 0)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setAccessibleName("Cancel the running operation")
        self.cancel_button.setAccessibleDescription(
            "Stops the catalogue build or the disc build. A part-written new image is deleted; "
            "your original is never touched."
        )
        self.cancel_button.hide()
        footer.addWidget(self.cancel_button, 0)
        root.addLayout(footer)

        self.button_box = QDialogButtonBox(QDialogButtonBox.Close)
        root.addWidget(self.button_box)

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QDialog#ps2DiscStudioDialog QLabel#panelTitle { font-size: 17px; font-weight: 600; }
            QDialog#ps2DiscStudioDialog QLabel#mutedLabel { color: #91a0b5; }
            QDialog#ps2DiscStudioDialog QLabel#discBoundary {
                background: #10261b; border: 1px solid #1f5a3a; border-radius: 6px;
                padding: 9px; color: #39d98a;
            }
            QDialog#ps2DiscStudioDialog QLabel#discInfoCard,
            QDialog#ps2DiscStudioDialog QLabel#exportReceiptCard,
            QDialog#ps2DiscStudioDialog QLabel#caveatCard {
                background: #101827; border: 1px solid #22304a; border-radius: 6px; padding: 9px;
            }
            QDialog#ps2DiscStudioDialog QLabel#refusalLabel { color: %s; }
            QDialog#ps2DiscStudioDialog QTableView, QDialog#ps2DiscStudioDialog QTableWidget,
            QDialog#ps2DiscStudioDialog QPlainTextEdit {
                background: %s; alternate-background-color: %s; color: %s;
            }
            """
            % (_INVALID_COLOUR, _TABLE_BASE, _TABLE_ALTERNATE, _TABLE_TEXT)
        )

    def _connect(self) -> None:
        self.open_button.clicked.connect(self._choose_image)
        self.cancel_button.clicked.connect(self._cancel_running)
        self.button_box.rejected.connect(self.reject)

    # -- background operations -----------------------------------------

    def _start(
        self,
        verb: str,
        title: str,
        operation: Callable[[Callable[[str], None], Any], object],
        done: Callable[[object], None],
        failure_note: str = "Your disc image was not changed.",
    ) -> None:
        """Hand one host operation to the pool and settle when it lands."""

        self._busy = True
        self._busy_verb = verb
        self._task_title = title
        self._task_note = failure_note
        self._task_done = done
        self._task_outcome = None
        self._task_error = None
        self._cancel = _cancel_token()
        self.status_label.setStyleSheet("")
        self._status(f"{verb}…")
        self.progress_bar.show()
        self.cancel_button.show()
        self._refresh_controls()
        task = _Task(operation, self._cancel)
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
            self._task_outcome, self._task_error, self._task_done, self._task_title, self._task_note,
        )
        cancelled = bool(self._cancel is not None and getattr(self._cancel, "cancelled", False))
        self._task = None
        self._task_outcome = None
        self._task_error = None
        self._task_done = None
        self._cancel = None
        self._busy = False
        self.progress_bar.hide()
        self.cancel_button.hide()
        if error is not None:
            self._refresh_controls()
            self.status_label.setStyleSheet(f"color: {_WARN_COLOUR if cancelled else _INVALID_COLOUR};")
            self._status(error)
            if not cancelled:
                QMessageBox.warning(self, title, f"{error}\n\n{note}")
            return
        if done is not None:
            done(outcome)
        self._refresh_controls()

    def _cancel_running(self) -> None:
        if self._busy and self._cancel is not None:
            self._cancel.cancel()
            self._status(f"Cancelling {self._busy_verb.lower()}…")

    # -- opening -------------------------------------------------------

    def _choose_image(self) -> None:
        if self._busy:
            return
        selected, _filter = QFileDialog.getOpenFileName(
            self, "Open a PlayStation 2 disc image", str(Path.home()), self.host.OPEN_FILTER,
        )
        if selected:
            self._open_path(Path(selected))

    def _open_path(self, path: Path) -> None:
        if self._busy:
            return
        self._plans.clear()
        self._stale.clear()
        self._plan_errors.clear()
        self._receipt = None
        self.build_page.receipt_label.hide()
        self.info_label.setText(f"Reading {path.name}…")
        self._start(
            "Opening the disc image",
            "That disc image could not be opened",
            lambda stage, _cancel: self.host.open(path, stage),
            self._opened,
        )

    def _opened(self, _identity: object) -> None:
        for tab in self.tabs.values():
            tab.disc_changed()
        self._refresh_info()
        self.build_page.destination.setText(
            str((self.host.source_path or Path.home()).parent / suggested_destination(self.host.identity().name))
        )
        self._refresh_queue()
        self.status_label.setStyleSheet("")
        self._status(self.host.identity().headline)

    def _refresh_info(self) -> None:
        if not self.host.is_open:
            self.info_label.setText("No disc image is open yet.")
            return
        identity = self.host.identity()
        lines = [str(getattr(identity, "headline", ""))]
        if not getattr(identity, "supported", True):
            lines.append(UNSUPPORTED_DISC_NOTE)
        elif not getattr(identity, "retail_boot_elf", True):
            lines.append("The boot ELF differs from the retail digest: a modified disc. Catalogues still "
                         "build from it and every patcher re-checks its targets against these bytes.")
        for lane in self.host.lanes():
            tab = self.tabs.get(lane.id)
            scope = tab.scope() if tab is not None else "default"
            try:
                state = self.host.catalogue_state(lane.id, scope)
            except ValidationError as exc:
                lines.append(f"{lane.title}: {exc}")
                continue
            lines.append(catalogue_status_text(lane.title, bool(getattr(state, "built", False)),
                                               str(getattr(state, "summary", "")), getattr(state, "seconds", None)))
        self.info_label.setText("\n".join(line for line in lines if line))

    # -- catalogues (called by the tabs) --------------------------------

    def build_catalogue(self, lane_id: str, scope: str) -> None:
        if self._busy or not self.host.is_open:
            return
        lane = self.host.lane(lane_id)
        self._start(
            f"Building the {lane.title} catalogue",
            f"The {lane.title} catalogue could not be built",
            lambda stage, cancel: self.host.build_catalogue(lane_id, scope, stage, cancel),
            lambda _state: self._catalogue_built(lane_id),
            failure_note="Nothing was kept from the interrupted build; your disc image was not changed.",
        )

    def _catalogue_built(self, lane_id: str) -> None:
        tab = self.tabs.get(lane_id)
        if tab is not None:
            tab.catalogue_changed()
        self._refresh_info()
        self.status_label.setStyleSheet(f"color: {_MATCH_COLOUR};")
        self._status(f"{self.host.lane(lane_id).title} catalogue built from your disc.")

    # -- recipes (called by the tabs) -------------------------------------

    def recipe_changed(self, lane_id: str) -> None:
        """A tab added or removed an edit: its plan, if any, no longer describes the recipe."""
        if lane_id in self._plans:
            self._stale.add(lane_id)
        self._plan_errors.pop(lane_id, None)
        self._receipt = None
        self.build_page.receipt_label.hide()
        self._refresh_queue()
        self._refresh_controls()

    def edits_by_lane(self) -> Dict[str, int]:
        return {lane_id: len(tab.staged()) for lane_id, tab in self.tabs.items()}

    def scopes(self) -> Dict[str, str]:
        return {lane_id: tab.scope() for lane_id, tab in self.tabs.items()}

    def check_lane(self, lane_id: str) -> None:
        """One lane's dry run, from its tab's Check button."""
        if self._busy or not self.host.is_open:
            return
        tab = self.tabs[lane_id]
        edits = list(tab.staged())
        scope = tab.scope()
        lane = self.host.lane(lane_id)
        self._start(
            f"Checking the {lane.title} recipe",
            f"The {lane.title} recipe was refused",
            lambda stage, cancel: self.host.plan_lane(lane_id, edits, scope, stage, cancel),
            lambda outcome: self._planned(lane_id, outcome),
            failure_note="Nothing was written. Fix the edit the sentence above names and check again.",
        )

    def _planned(self, lane_id: str, outcome: object) -> None:
        self._plans[lane_id] = outcome
        self._stale.discard(lane_id)
        self._plan_errors.pop(lane_id, None)
        tab = self.tabs.get(lane_id)
        if tab is not None:
            tab.plan_changed(outcome, None)
        self._refresh_queue()
        self.status_label.setStyleSheet(f"color: {_MATCH_COLOUR};")
        self._status(f"{self.host.lane(lane_id).title}: {getattr(outcome, 'summary', 'checked')}")

    def _check_everything(self) -> None:
        """Dry-run every lane with staged edits, one after another, in one task."""
        if self._busy or not self.host.is_open:
            return
        work = [(lane_id, list(tab.staged()), tab.scope()) for lane_id, tab in self.tabs.items() if tab.staged()]
        if not work:
            self._status("Nothing is staged yet.")
            return
        host = self.host

        def operation(stage: Callable[[str], None], cancel: Any) -> Dict[str, Any]:
            outcomes: Dict[str, Any] = {}
            errors: Dict[str, str] = {}
            for lane_id, edits, scope in work:
                if cancel is not None and getattr(cancel, "cancelled", False):
                    from mod_editor.core.ps2_disc_studio_service import Cancelled

                    raise Cancelled("Checking was cancelled.")
                try:
                    outcomes[lane_id] = host.plan_lane(lane_id, edits, scope, stage, cancel)
                except ValidationError as exc:
                    errors[lane_id] = str(exc).strip() or "refused"
            return {"outcomes": outcomes, "errors": errors}

        self._start("Checking every staged recipe", "The recipes could not be checked",
                    operation, self._checked_everything,
                    failure_note="Nothing was written.")

    def _checked_everything(self, result: object) -> None:
        outcomes = dict(getattr(result, "get", lambda *_: {})("outcomes") or {})
        errors = dict(result.get("errors") or {}) if isinstance(result, dict) else {}
        for lane_id, outcome in outcomes.items():
            self._plans[lane_id] = outcome
            self._stale.discard(lane_id)
            self._plan_errors.pop(lane_id, None)
            tab = self.tabs.get(lane_id)
            if tab is not None:
                tab.plan_changed(outcome, None)
        for lane_id, message in errors.items():
            self._plans.pop(lane_id, None)
            self._plan_errors[lane_id] = message
            tab = self.tabs.get(lane_id)
            if tab is not None:
                tab.plan_changed(None, message)
        self._refresh_queue()
        if errors:
            names = ", ".join(self.host.lane(lane_id).title for lane_id in errors)
            self.status_label.setStyleSheet(f"color: {_INVALID_COLOUR};")
            self._status(f"Refused: {names}. See the Build queue and the lane tab for the sentence.")
        else:
            self.status_label.setStyleSheet(f"color: {_MATCH_COLOUR};")
            self._status("Every staged recipe checked clean against your disc. Nothing was written.")

    def _plans_ready(self) -> bool:
        staged = {lane_id for lane_id, count in self.edits_by_lane().items() if count}
        return bool(staged) and all(lane_id in self._plans and lane_id not in self._stale for lane_id in staged)

    def _refresh_queue(self) -> None:
        self.build_page.refresh(self.edits_by_lane(), self._plans, sorted(self._stale), self._plan_errors)
        self._refresh_estimate()

    def _refresh_estimate(self) -> None:
        if not self.host.is_open:
            self.build_page.estimate_label.setText("")
            return
        text = self.build_page.destination.text().strip()
        if not text:
            self.build_page.estimate_label.setText("Choose a destination to see the free-space check.")
            return
        steps = sum(1 for count in self.edits_by_lane().values() if count) or 1
        try:
            estimate = self.host.estimate(steps, Path(text))
        except ValidationError as exc:
            self.build_page.estimate_label.setText(str(exc))
            return
        self.build_page.estimate_label.setText(
            f"{getattr(estimate, 'sentence', '')}\n{getattr(estimate, 'minutes_hint', '')}"
        )

    # -- building ------------------------------------------------------

    def _choose_destination(self) -> None:
        if self._busy:
            return
        current = self.build_page.destination.text().strip()
        start = current or str(Path.home() / suggested_destination(
            self.host.identity().name if self.host.is_open else "nfl2k5-ps2"))
        selected, _filter = QFileDialog.getSaveFileName(
            self, "Name the new disc image", start, self.host.SAVE_FILTER,
            options=QFileDialog.DontConfirmOverwrite,
        )
        if selected:
            self.build_page.destination.setText(selected)

    def _build(self) -> None:
        if self._busy or not self.host.is_open or not self._plans_ready():
            return
        destination = Path(self.build_page.destination.text().strip())
        if not str(destination).strip():
            self._status("Choose a destination for the new image first.")
            return
        plans = [self._plans[lane_id] for lane_id in LANE_ORDER if lane_id in self._plans
                 and self.edits_by_lane().get(lane_id)]
        scopes = self.scopes()
        self._receipt = None
        self.build_page.receipt_label.hide()
        self._start(
            "Building the new disc image",
            "The new disc image could not be built",
            lambda stage, cancel: self.host.build(plans, destination, stage, cancel, scopes),
            self._built,
            failure_note="Whatever the build had created has been removed. Your original disc image was not changed.",
        )

    def _built(self, receipt: object) -> None:
        self._receipt = receipt
        self.build_page.receipt_label.setText(receipt_text(receipt))
        self.build_page.receipt_label.show()
        self.tab_widget.setCurrentWidget(self.build_page)
        passed = bool(getattr(receipt, "all_verified", False))
        self.status_label.setStyleSheet(f"color: {_MATCH_COLOUR if passed else _WARN_COLOUR};")
        self._status(str(getattr(receipt, "message", "Built.")))

    def _open_folder(self) -> None:
        if self._receipt is None:
            return
        folder = Path(getattr(self._receipt, "destination", Path.home())).parent
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    # -- shared --------------------------------------------------------

    def action_state(self) -> Ps2DiscStudioActionState:
        identity = self.host.identity() if self.host.is_open else None
        built_any = False
        if self.host.is_open:
            for lane in self.host.lanes():
                tab = self.tabs.get(lane.id)
                try:
                    if getattr(self.host.catalogue_state(lane.id, tab.scope() if tab else "default"),
                               "built", False):
                        built_any = True
                        break
                except ValidationError:
                    continue
        return ps2_disc_studio_action_state(
            disc_open=self.host.is_open,
            supported=bool(getattr(identity, "supported", False)),
            busy=self._busy,
            catalogue_built=built_any,
            staged_count=sum(self.edits_by_lane().values()),
            plans_ready=self._plans_ready(),
            built=self._receipt is not None,
        )

    def _refresh_controls(self) -> None:
        if getattr(self, "build_page", None) is None:
            return      # a tab is still being constructed; the shell refreshes once it is up
        state = self.action_state()
        self.open_button.setEnabled(state.can_open)
        self.build_page.check_button.setEnabled(state.can_check)
        self.build_page.build_button.setEnabled(state.can_build)
        self.build_page.open_folder_button.setEnabled(state.can_open_folder)
        self.build_page.destination.setEnabled(not self._busy)
        self.build_page.choose_button.setEnabled(not self._busy)
        for tab in self.tabs.values():
            tab.refresh_controls(state)

    def done(self, result: int) -> None:
        """Refuse to close while an operation is in flight."""

        if self._busy:
            self._status(f"{self._busy_verb} is still running. Cancel it first, or wait for it to finish.")
            return
        try:
            self.host.close()
        except Exception:  # pragma: no cover - closing must never block the window
            pass
        super().done(result)

    def _status(self, message: str) -> None:
        self.status_label.setText(message)
        self.status_label.setToolTip(message)


__all__ = [
    "BOUNDARY_NOTE",
    "BuildPage",
    "PYQT5_AVAILABLE",
    "Ps2DiscStudioActionState",
    "Ps2DiscStudioDialog",
    "Ps2DiscStudioHost",
    "UNSUPPORTED_DISC_NOTE",
    "catalogue_status_text",
    "ps2_disc_studio_action_state",
    "queue_summary_text",
    "receipt_text",
    "suggested_destination",
]
