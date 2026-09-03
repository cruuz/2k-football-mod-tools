"""Update notice shared by both editors.

Design rules, because this is the one piece of UI that talks to the internet:

* Nothing happens without the user acting. The check reports a version and
  opens a link. It never downloads, never installs, never restarts anything.
* It cannot block the app. The request runs on a pool thread and every failure
  is treated as "no news", so a bad connection is silence, not a dialog.
* It is switchable and says so. The Help menu carries a visible checkbox and
  the first automatic check explains what it does before doing it again.
* Dismissing a version means dismissing that version. Saying "Later" to
  beta-23 must not also hide beta-24.
"""

from __future__ import annotations

import os

from PyQt5.QtCore import QObject, QRunnable, QSettings, Qt, QThreadPool, pyqtSignal
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtCore import QUrl
from PyQt5.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
)

from mod_editor.core import update_check

SETTINGS_ORGANISATION = "2K Football Mod Tools"
SETTINGS_APPLICATION = "updates"
KEY_ENABLED = "check_automatically"
KEY_DISMISSED = "dismissed_tag"
KEY_PROMPTED = "explained_once"
# Set to 1 / true / yes to keep a run entirely offline (CI, scripted use, a
# locked-down machine). It wins over the saved preference and never writes it.
ENV_DISABLE = "MOD_STUDIO_NO_UPDATE_CHECK"


def _settings() -> QSettings:
    return QSettings(
        QSettings.IniFormat, QSettings.UserScope,
        SETTINGS_ORGANISATION, SETTINGS_APPLICATION,
    )


def automatic_checks_enabled() -> bool:
    if os.environ.get(ENV_DISABLE, "").strip().lower() in {"1", "true", "yes"}:
        return False
    value = _settings().value(KEY_ENABLED, True)
    if isinstance(value, str):
        return value.strip().lower() not in {"false", "0", "no"}
    return bool(value)


def set_automatic_checks_enabled(enabled: bool) -> None:
    settings = _settings()
    settings.setValue(KEY_ENABLED, bool(enabled))
    settings.sync()


def _dismissed_tag() -> str:
    value = _settings().value(KEY_DISMISSED, "")
    return value if isinstance(value, str) else ""


def _dismiss_tag(tag: str) -> None:
    settings = _settings()
    settings.setValue(KEY_DISMISSED, tag)
    settings.sync()


class _Signals(QObject):
    done = pyqtSignal(object)


class _CheckTask(QRunnable):
    """One request, off the GUI thread, that cannot raise into Qt."""

    def __init__(self, current_tag: str) -> None:
        super().__init__()
        # Owned from the GUI thread until the result has been delivered (see
        # start_check). With the pool's default autoDelete the runnable, and
        # with it the GUI-thread `signals` object, was destroyed from the worker
        # thread while the queued `done` emission was still in flight.
        self.setAutoDelete(False)
        self.signals = _Signals()
        self._current_tag = current_tag

    def run(self) -> None:  # pragma: no cover - exercised through the pool
        try:
            status = update_check.check(self._current_tag)
        except Exception:  # noqa: BLE001 - a failed check is never fatal
            status = update_check.UpdateStatus(
                available=False, current_tag=self._current_tag,
                detail="The update check could not run.",
            )
        try:
            self.signals.done.emit(status)
        except RuntimeError:
            # QApplication teardown can delete the QObject receiver while an
            # already-running network task is finishing.  The result has no
            # live UI consumer at that point, so dropping it is the correct
            # quiet shutdown behavior promised by this worker.
            return


# Checks in flight, held so that each task and its signal object outlive the
# worker thread and die on the GUI thread, after `done` has been delivered.
_LIVE_CHECKS: set[_CheckTask] = set()


def start_check(current_tag: str, on_result) -> None:
    """Run a check on a pool thread and hand the result back on the GUI thread."""

    task = _CheckTask(current_tag)
    task.signals.done.connect(on_result)
    task.signals.done.connect(lambda _status, task=task: _LIVE_CHECKS.discard(task))
    _LIVE_CHECKS.add(task)
    QThreadPool.globalInstance().start(task)


class UpdateBanner(QFrame):
    """A one-line strip that appears only when there is something to say."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("updateBanner")
        self.setFrameShape(QFrame.NoFrame)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._status: update_check.UpdateStatus | None = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)

        self.message = QLabel("")
        self.message.setObjectName("updateBannerText")
        self.message.setWordWrap(True)
        self.message.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.message, 1)

        self.download_button = QPushButton("Get the update")
        self.download_button.setObjectName("primaryButton")
        self.download_button.setToolTip(
            "Opens the downloads page in your browser. Nothing is installed for "
            "you."
        )
        self.download_button.clicked.connect(self._open_downloads)
        layout.addWidget(self.download_button)

        self.later_button = QPushButton("Later")
        self.later_button.setObjectName("secondaryButton")
        self.later_button.setToolTip(
            "Hides this until the next release. You can always use "
            "Help then Check for Updates."
        )
        self.later_button.clicked.connect(self._dismiss)
        layout.addWidget(self.later_button)

        self.hide()

    def show_status(self, status: update_check.UpdateStatus) -> None:
        """Show the strip only for a new version the user has not waved off."""

        self._status = status
        if not status.available or not status.latest_tag:
            self.hide()
            return
        if status.latest_tag == _dismissed_tag():
            self.hide()
            return
        headline = f"Update available: {status.latest_tag}"
        if status.title:
            headline += f" - {status.title}"
        headline += f". You are running {status.current_tag}."
        self.message.setText(headline)
        self.show()

    def _open_downloads(self) -> None:
        if self._status is not None:
            QDesktopServices.openUrl(QUrl(self._status.url))

    def _dismiss(self) -> None:
        if self._status is not None and self._status.latest_tag:
            _dismiss_tag(self._status.latest_tag)
        self.hide()


def report_manual_check(parent, status: update_check.UpdateStatus) -> None:
    """What a user sees after asking for a check themselves.

    A manual check always answers, including "you are up to date". Silence
    after clicking a button reads as a broken button.
    """

    box = QMessageBox(parent)
    box.setWindowTitle("Check for Updates")
    box.setIcon(QMessageBox.Information)
    box.setText(status.headline)

    if status.available and status.latest_tag:
        detail = f"You are running {status.current_tag}."
        if status.title:
            detail += f"\n\n{status.title}"
        box.setInformativeText(detail)
        open_button = box.addButton("Get the update", QMessageBox.AcceptRole)
        box.addButton("Close", QMessageBox.RejectRole)
        box.exec_()
        if box.clickedButton() is open_button:
            QDesktopServices.openUrl(QUrl(status.url))
        return

    if status.detail:
        box.setInformativeText(status.detail)
    box.addButton("Close", QMessageBox.RejectRole)
    box.exec_()


def explain_automatic_checks_once(parent) -> None:
    """Say what the automatic check does, the first time it runs.

    Contacting a server is not something the user typed, so it is disclosed
    rather than assumed. Shown once; the Help menu keeps the switch afterwards.
    """

    settings = _settings()
    if settings.value(KEY_PROMPTED, False) in (True, "true", "1"):
        return
    settings.setValue(KEY_PROMPTED, True)
    settings.sync()

    box = QMessageBox(parent)
    box.setWindowTitle("Update checks")
    box.setIcon(QMessageBox.Information)
    box.setText("This app checks GitHub for a newer release when it starts.")
    box.setInformativeText(
        "It sends no information about you or your game, and it never "
        "downloads or installs anything. Turn it off any time under "
        "Help then Check for updates automatically."
    )
    box.addButton("OK", QMessageBox.AcceptRole)
    box.exec_()
