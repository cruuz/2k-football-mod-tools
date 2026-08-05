"""Turn an unhandled exception into a message the user can act on.

Two things make this necessary rather than nice to have.

PyQt5 aborts the process when an exception escapes a slot and no
``sys.excepthook`` is installed. Nothing is printed anywhere the user can see,
because these editors are started from a desktop icon or a ``.bat``/``.command``
wrapper with no console attached. The whole window simply disappears. Installing
a hook is also what stops the abort: PyQt5 calls the hook instead of calling
``qFatal`` when one is present, so the same change that reports the error keeps
the editor running.

The other half is that the report has to survive the dialog being closed. A
traceback the user cannot copy is a bug report nobody can act on, so it is
written to a file first and the path is shown.

Nothing here may raise. A crash handler that crashes replaces a useful message
with a worse one, so every step is guarded and falls back to stderr.
"""

from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path
import sys
import traceback
from typing import Callable

#: Kept small on purpose. The dialog has to stay readable on a laptop screen,
#: and the full traceback is in the log file either way.
_DIALOG_TRACEBACK_LIMIT = 4000

#: Faults already shown to the user, so a repeating one does not stack dialogs.
_ALREADY_SHOWN: set[str] = set()


def signature(exc_type, tb) -> str:
    """What makes two reports "the same fault" for dialog purposes.

    Something thrown from a paint or timer handler fires again every frame. Each
    dialog is modal, so without this the second one queues behind the first and
    the editor becomes a wall of identical boxes nobody can dismiss. The log
    still records every occurrence; only the interruption is suppressed.
    """

    frame = tb
    while frame is not None and frame.tb_next is not None:
        frame = frame.tb_next
    if frame is None:
        return getattr(exc_type, "__name__", str(exc_type))
    code = frame.tb_frame.f_code
    return f"{getattr(exc_type, '__name__', exc_type)}:{code.co_filename}:{frame.tb_lineno}"


def log_directory(app_name: str) -> Path:
    """Where reports are written, following each platform's convention."""

    slug = app_name.lower().replace(" ", "-")
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Logs"
    else:
        base = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state")
    return base / slug


def format_report(exc_type, exc, tb, app_name: str, *, when: str | None = None) -> str:
    """One self-contained report: what broke, where, and on what."""

    stamp = when or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    body = "".join(traceback.format_exception(exc_type, exc, tb))
    return (
        f"{app_name}\n"
        f"time: {stamp}\n"
        f"python: {sys.version.split()[0]} on {sys.platform}\n"
        f"\n{body}"
    )


def write_report(report: str, app_name: str, *, directory: Path | None = None) -> Path | None:
    """Append the report to the log, returning the path, or None if it cannot."""

    target = (directory or log_directory(app_name)) / "errors.log"
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as handle:
            handle.write(report)
            handle.write("\n" + "-" * 60 + "\n")
        return target
    except OSError:
        # A read-only or missing home directory is not a reason to lose the
        # message; the caller still shows it on screen.
        return None


def summary_lines(app_name: str, saved_to: Path | None) -> tuple[str, str, str]:
    """The three pieces of dialog text: title, headline, and detail.

    Written for somebody who did not write the software: say what happened, say
    the thing they will worry about first, then say what to do.
    """

    title = f"{app_name} hit an unexpected error"
    headline = "Something went wrong. Your original game files were not changed."
    if saved_to is not None:
        detail = (
            f"The editor is still running, so you can keep working or restart it.\n\n"
            f"Details were saved to:\n{saved_to}\n\n"
            f"If this keeps happening, include that file in a bug report."
        )
    else:
        detail = (
            "The editor is still running, so you can keep working or restart it.\n\n"
            "The details below could not be saved to a file. Copy them into a bug "
            "report if this keeps happening."
        )
    return title, headline, detail


#: Qt platform plugins that draw to nothing a person is looking at. A modal
#: dialog on one of these waits for a click that can never arrive, which turns a
#: reported error into a hung process.
_HEADLESS_PLATFORMS = frozenset({"offscreen", "minimal", "minimalegl", "vnc"})


def dialog_is_possible(platform_name: str | None, environment=None) -> bool:
    """Whether a modal dialog can actually be dismissed by somebody.

    ``QMessageBox.exec_`` blocks until the user closes it. Under the offscreen
    platform, or in a test run, nobody ever will, so the call never returns and
    the whole run stops. The log and stderr do not depend on this; only the
    interruption does.
    """

    if environment is None:
        environment = os.environ
    if environment.get("MOD_STUDIO_NO_ERROR_DIALOG"):
        return False
    # pytest exports this for the duration of every test.
    if "PYTEST_CURRENT_TEST" in environment:
        return False
    return (platform_name or "").lower() not in _HEADLESS_PLATFORMS


def _show_dialog(app_name: str, saved_to: Path | None, report: str) -> bool:
    """Put the report on screen. False when there is no GUI to put it on."""

    try:
        from PyQt5.QtWidgets import QApplication, QMessageBox
    except Exception:  # noqa: BLE001 - no Qt available, caller falls back
        return False
    application = QApplication.instance()
    if application is None:
        return False
    try:
        platform_name = application.platformName()
    except Exception:  # noqa: BLE001
        platform_name = None
    if not dialog_is_possible(platform_name):
        return False
    try:
        title, headline, detail = summary_lines(app_name, saved_to)
        box = QMessageBox()
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle(title)
        box.setText(headline)
        box.setInformativeText(detail)
        box.setDetailedText(report[:_DIALOG_TRACEBACK_LIMIT])
        box.setStandardButtons(QMessageBox.Ok)
        box.exec_()
        return True
    except Exception:  # noqa: BLE001 - a failed dialog must not mask the error
        return False


def handle(exc_type, exc, tb, *, app_name: str, directory: Path | None = None,
           show_dialog: bool = True) -> None:
    """The hook body, exposed separately so it can be tested without Qt.

    ``show_dialog`` is off in tests and headless checks. The dialog is modal by
    design, and with no user to dismiss it the call would never return.
    """

    # Ctrl+C is a request to quit, not a fault. Reporting it as a crash would be
    # both wrong and, in a terminal, impossible to escape.
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc, tb)
        return
    try:
        report = format_report(exc_type, exc, tb, app_name)
    except Exception:  # noqa: BLE001
        sys.__excepthook__(exc_type, exc, tb)
        return
    saved_to = write_report(report, app_name, directory=directory)
    # stderr always gets it: when a console is attached it is the fastest thing
    # to read, and it is the only channel left if the dialog cannot be shown.
    try:
        sys.stderr.write(report)
        sys.stderr.flush()
    except Exception:  # noqa: BLE001
        pass
    if not show_dialog:
        return
    key = signature(exc_type, tb)
    if key in _ALREADY_SHOWN:
        return
    _ALREADY_SHOWN.add(key)
    _show_dialog(app_name, saved_to, report)


def install(app_name: str, *, directory: Path | None = None) -> Callable:
    """Route unhandled exceptions to :func:`handle`, returning the old hook."""

    previous = sys.excepthook

    def hook(exc_type, exc, tb) -> None:
        handle(exc_type, exc, tb, app_name=app_name, directory=directory)

    sys.excepthook = hook
    return previous


__all__ = [
    "format_report",
    "handle",
    "install",
    "dialog_is_possible",
    "log_directory",
    "signature",
    "summary_lines",
    "write_report",
]
