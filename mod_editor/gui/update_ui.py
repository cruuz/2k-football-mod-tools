"""Update notice shared by both editors.

Design rules, because this is the one piece of UI that talks to the internet:

* Nothing happens without the user acting. The check reports a version. The
  user chooses between installing it from inside the app (``Update now``),
  opening the downloads page, or waiting. No download starts on its own.
* It cannot block the app. Requests and downloads run on a pool thread and a
  failed check is treated as "no news", so a bad connection is silence, not a
  dialog. A failed update is one sentence in the banner, nothing worse.
* It is switchable and says so. The Help menu carries a visible checkbox and
  the first automatic check explains what it does before doing it again.
* Dismissing a version means dismissing that version. Saying "Later" to
  beta-23 must not also hide beta-24.
* An update is verified before it is installed: the file is compared with the
  SHA-256 the release published, and discarded when it does not match.
"""

from __future__ import annotations

import os

from PyQt5.QtCore import (
    QObject,
    QRunnable,
    QSettings,
    Qt,
    QThreadPool,
    QTimer,
    QUrl,
    pyqtSignal,
)
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
)

from mod_editor.core import self_update, update_check

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


class _UpdateSignals(QObject):
    progress = pyqtSignal(str, int, int)
    done = pyqtSignal(object, str)


class _UpdateTask(QRunnable):
    """Download, verify and hand off one release, off the GUI thread."""

    def __init__(self, document: dict, product: str, install: self_update.InstallKind) -> None:
        super().__init__()
        self.setAutoDelete(False)
        self.signals = _UpdateSignals()
        self._document = document
        self._product = product
        self._install = install

    def run(self) -> None:  # pragma: no cover - exercised through the pool
        try:
            plan = self_update.run_update(
                self._document, self._product, install=self._install,
                progress=self.signals.progress.emit,
            )
        except self_update.SelfUpdateError as exc:
            self._finish(None, str(exc))
            return
        except Exception as exc:  # noqa: BLE001 - never raise into Qt
            self._finish(None, f"The update could not be installed: {exc}")
            return
        self._finish(plan, "")

    def _finish(self, plan, error: str) -> None:
        try:
            self.signals.done.emit(plan, error)
        except RuntimeError:
            return


_LIVE_UPDATES: set[_UpdateTask] = set()


class UpdateBanner(QFrame):
    """A one-line strip that appears only when there is something to say.

    ``Update now`` is offered when this copy knows how to replace itself (the
    Windows installer layout, or an unpacked release folder) and the release
    carries the matching file. A git checkout, or a folder this updater does
    not recognise, only gets ``Get the update``.
    """

    #: Emitted after an update has been handed off, with the plan.
    update_ready = pyqtSignal(object)

    def __init__(self, parent=None, *, product: str = "2k5") -> None:
        super().__init__(parent)
        self.setObjectName("updateBanner")
        self.setFrameShape(QFrame.NoFrame)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._status: update_check.UpdateStatus | None = None
        self._product = product
        self._install = self_update.detect_install(product=product)
        self._task: _UpdateTask | None = None
        self.plan: self_update.UpdatePlan | None = None
        self.last_error = ""
        # Replaceable hooks: confirmation and quitting are the two things a
        # test must not do for real.
        self.confirm = self._confirm_dialog
        self.request_quit = self._request_quit

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)

        self.message = QLabel("")
        self.message.setObjectName("updateBannerText")
        self.message.setWordWrap(True)
        self.message.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.message, 1)

        self.update_button = QPushButton("Update now")
        self.update_button.setObjectName("primaryButton")
        self.update_button.setToolTip(
            "Downloads the new release, checks it against its published "
            "SHA-256, installs it over this copy and reopens the studio."
        )
        self.update_button.clicked.connect(self.start_update)
        layout.addWidget(self.update_button)

        self.download_button = QPushButton("Get the update")
        self.download_button.setObjectName("secondaryButton")
        self.download_button.setToolTip(
            "Opens the downloads page in your browser instead."
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

    # ------------------------------------------------------------ state

    @property
    def install(self) -> self_update.InstallKind:
        return self._install

    def can_self_update(self, status: update_check.UpdateStatus) -> bool:
        """Whether ``Update now`` would have something to do for this status."""
        if not status.available or not status.latest_tag:
            return False
        try:
            self_update.plan_update(status.release_document(), self._install, self._product)
        except self_update.SelfUpdateError:
            return False
        return True

    def show_status(self, status: update_check.UpdateStatus, *, force: bool = False) -> None:
        """Show the strip only for a new version the user has not waved off."""

        self._status = status
        if not status.available or not status.latest_tag:
            self.hide()
            return
        if status.latest_tag == _dismissed_tag() and not force:
            self.hide()
            return
        headline = f"Update available: {status.latest_tag}"
        if status.title:
            headline += f" - {status.title}"
        headline += f". You are running {status.current_tag}."
        self.message.setText(headline)
        self.update_button.setVisible(self.can_self_update(status))
        self._set_busy(False)
        self.show()

    def _set_busy(self, busy: bool) -> None:
        for button in (self.update_button, self.download_button, self.later_button):
            button.setEnabled(not busy)

    # ------------------------------------------------------------ actions

    def _open_downloads(self) -> None:
        if self._status is not None:
            QDesktopServices.openUrl(QUrl(self._status.url))

    def _dismiss(self) -> None:
        if self._status is not None and self._status.latest_tag:
            _dismiss_tag(self._status.latest_tag)
        self.hide()

    def _confirm_dialog(self, plan: self_update.UpdatePlan) -> bool:
        if not self.isVisible():
            return True
        box = QMessageBox(self.window())
        box.setWindowTitle("Update now")
        box.setIcon(QMessageBox.Question)
        box.setText(f"Install {plan.tag} now?")
        if plan.install.kind == "windows-installer":
            how = ("The studio downloads the installer, checks it against its published "
                   "SHA-256, then closes. The installer runs on its own, into the same "
                   "folder, and reopens the studio when it is done.")
        else:
            how = ("The studio downloads the release, checks it against its published "
                   "SHA-256, unpacks it beside this folder, switches the folders and "
                   "starts the new version. The previous version stays next to it as "
                   f"{plan.install.root.name}.previous until you delete it.")
        box.setInformativeText(f"{how}\n\nSave your work first: the studio closes to finish.\n\n"
                               f"Download: {plan.asset.name} ({plan.size_mb:.0f} MB)")
        install_button = box.addButton("Install and restart", QMessageBox.AcceptRole)
        box.addButton("Not now", QMessageBox.RejectRole)
        box.exec_()
        return box.clickedButton() is install_button

    def start_update(self) -> bool:
        """Confirm, then download + verify + install on a pool thread."""
        if self._status is None or self._task is not None:
            return False
        document = self._status.release_document()
        try:
            plan = self_update.plan_update(document, self._install, self._product)
        except self_update.SelfUpdateError as exc:
            self.last_error = str(exc)
            self.message.setText(str(exc))
            self.update_button.setVisible(False)
            return False
        if not self.confirm(plan):
            return False
        self._set_busy(True)
        self.message.setText(f"Downloading {plan.asset.name} ({plan.size_mb:.0f} MB)…")
        task = _UpdateTask(document, self._product, self._install)
        task.signals.progress.connect(self._on_progress)
        task.signals.done.connect(self._on_done)
        task.signals.done.connect(lambda *_a, task=task: _LIVE_UPDATES.discard(task))
        self._task = task
        _LIVE_UPDATES.add(task)
        QThreadPool.globalInstance().start(task)
        return True

    def _on_progress(self, message: str, done: int, total: int) -> None:
        if total > 1 and done <= total:
            self.message.setText(f"{message}… {100 * done // total}%")
        else:
            self.message.setText(f"{message}…")

    def _on_done(self, plan, error: str) -> None:
        self._task = None
        if plan is None:
            self.last_error = error
            self.message.setText(f"The update did not install: {error}")
            self._set_busy(False)
            return
        self.plan = plan
        if plan.install.kind == "windows-installer":
            self.message.setText(
                f"{plan.tag} is downloaded and verified. The studio closes now; the "
                "installer runs on its own and reopens it when it is done."
            )
        else:
            self.message.setText(
                f"{plan.tag} is installed and starting. This window closes now."
            )
        self.update_ready.emit(plan)
        QTimer.singleShot(1200, self.request_quit)

    def _request_quit(self) -> None:
        app = QApplication.instance()
        if app is None:
            return
        app.closeAllWindows()
        still_open = [
            widget for widget in app.topLevelWidgets()
            if widget.isWindow() and widget.isVisible() and widget is not self
        ]
        if still_open:
            # A close was refused (unsaved work, a running build). The hand-off
            # already happened, so say what finishes it rather than forcing it.
            if self.plan is not None and self.plan.install.kind == "windows-installer":
                self.message.setText(
                    "The update installs as soon as you close the studio. It waits "
                    "up to ten minutes."
                )
            else:
                self.message.setText(
                    "The new version is already running. Close this window when "
                    "you are done here."
                )
            return
        app.quit()

    def wait_idle(self, timeout_ms: int = 60_000) -> bool:
        """Test helper: spin until the update task has reported back."""
        app = QApplication.instance()
        from PyQt5.QtCore import QDeadlineTimer
        deadline = QDeadlineTimer(timeout_ms)
        while self._task is not None and not deadline.hasExpired():
            app.processEvents()
            QThreadPool.globalInstance().waitForDone(50)
        return self._task is None


def report_manual_check(parent, status: update_check.UpdateStatus, banner: UpdateBanner | None = None) -> None:
    """What a user sees after asking for a check themselves.

    A manual check always answers, including "you are up to date". Silence
    after clicking a button reads as a broken button. When the banner knows how
    to install the release, the dialog offers that too.
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
        install_button = None
        if banner is not None and banner.can_self_update(status):
            install_button = box.addButton("Update now", QMessageBox.AcceptRole)
        open_button = box.addButton("Get the update", QMessageBox.ActionRole)
        box.addButton("Close", QMessageBox.RejectRole)
        box.exec_()
        if install_button is not None and box.clickedButton() is install_button:
            banner.show_status(status, force=True)
            banner.start_update()
        elif box.clickedButton() is open_button:
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
        "It sends no information about you or your game, and it downloads "
        "nothing on its own. When a newer release exists you can install it "
        "with one click, open the downloads page, or wait. Turn the check off "
        "any time under Help then Check for updates automatically."
    )
    box.addButton("OK", QMessageBox.AcceptRole)
    box.exec_()
