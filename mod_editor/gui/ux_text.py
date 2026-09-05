"""Shared plain-language UI pieces for the 2K5 Mod Studio pages.

Every page used to explain itself in its own words (XISO, default.xbe, retail, RSA
signature, cave, receipt).  The pieces here keep the few sentences that repeat on many
pages in one place, so they read the same everywhere:

* :func:`tab_title` -- escape a literal ``&`` for the controls that read it as a
  keyboard mnemonic (tabs, buttons, check boxes).  Sidebar rows and plain labels do
  not interpret it and must not be escaped.
* :data:`XEMU_LINE` / :data:`NOT_TESTED` -- the two qualifiers that belong beside every
  executable patch: it runs in xemu, and some changes have not been seen in-game yet.
* :class:`Details` -- a collapsed "Details ▸" section for the long technical story.
  Nothing is removed from a page: it moves under the button, which is a normal focusable
  tool button (Tab reaches it, Space / Enter toggles it).
* :func:`show_operation_error` -- one error dialog shape: a plain title, the real
  cause, a known ``Fix:`` when there is one, and the full text under Details.
* :func:`suggest_copy_name` -- the ``{stem} (modded).xiso.iso`` name a disc-copying
  page suggests next to the source, never reusing an existing file.
"""

from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QLabel, QMessageBox, QToolButton, QVBoxLayout, QWidget

#: The compatibility line every executable-patch page shows once.
XEMU_LINE = "For xemu; original Xbox support is not provided."

#: The qualifier next to a change nobody has watched in-game yet.
NOT_TESTED = "Not yet tested in-game"

#: Where a lost first-timer should ask.  The Help menu carries the same link.
DISCORD_HINT = "Share that text on the Discord if you need help."


def tab_title(text: str) -> str:
    """Escape a literal ampersand for a tab, button or check box caption."""

    return text.replace("&&", "&").replace("&", "&&")


def source_captions(is_image: bool) -> tuple[str, str]:
    """The source / output row captions for a page that takes a disc or a bare executable."""

    if is_image:
        return "Game disc (.iso)", "Save disc copy as"
    return "Game executable (default.xbe)", "Save executable copy as"


def write_caption(is_image: bool, disc_caption: str = "Make disc with these changes") -> str:
    """What the write button says: a disc copy, or a patched executable."""

    return disc_caption if is_image else "Save patched executable…"


class Details(QWidget):
    """A collapsed section behind a "Details ▸" button.

    ``content`` is the layout callers add their widgets to.  The button is a normal
    focusable QToolButton, so keyboard users reach it with Tab and open it with Space; the
    content stays in the widget tree either way and keeps whatever the user set in it.
    """

    toggled = pyqtSignal(bool)

    def __init__(self, title: str = "Details", parent: QWidget | None = None, *,
                 expanded: bool = False) -> None:
        super().__init__(parent)
        self._title = title
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(4)
        self.button = QToolButton()
        self.button.setCheckable(True)
        self.button.setAutoRaise(True)
        self.button.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.button.setFocusPolicy(Qt.StrongFocus)
        self.button.setAccessibleName(f"{title} (show or hide)")
        self.button.setCursor(Qt.PointingHandCursor)
        outer.addWidget(self.button, 0, Qt.AlignLeft)
        self.body = QWidget()
        self.content = QVBoxLayout(self.body)
        self.content.setContentsMargins(18, 2, 0, 4)
        self.content.setSpacing(6)
        outer.addWidget(self.body)
        self.button.toggled.connect(self._apply)
        self.button.setChecked(expanded)
        self._apply(expanded)

    def _apply(self, expanded: bool) -> None:
        self.body.setVisible(expanded)
        self.button.setText(f"{self._title} {'▾' if expanded else '▸'}")
        self.toggled.emit(expanded)

    def add_text(self, text: str, *, object_name: str = "throwMuted") -> QLabel:
        """Add one wrapped paragraph and return it."""

        label = QLabel(text)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        if object_name:
            label.setObjectName(object_name)
        self.content.addWidget(label)
        return label

    def set_expanded(self, expanded: bool) -> None:
        self.button.setChecked(bool(expanded))

    def is_expanded(self) -> bool:
        return self.button.isChecked()

    def set_title(self, title: str) -> None:
        self._title = title
        self._apply(self.button.isChecked())


# Known refusals a first-timer meets, and the one thing to do about each.  The matching is on
# the backend's own words; nothing here changes what is refused.
_FIX_HINTS: tuple[tuple[str, str], ...] = (
    ("already exists", "Fix: choose a new filename."),
    ("must not be the source", "Fix: choose a different output file."),
    ("target must not be the source", "Fix: choose a different output file."),
    ("neither retail nor this patch", "Fix: start from a disc this patch recognises, or turn that change off."),
    ("free space", "Fix: free up room where the copy is being written, or choose another folder."),
    ("Permission denied", "Fix: choose a folder you can write to."),
    ("not a regular file", "Fix: choose the disc file itself."),
    ("No such file", "Fix: check that the file is still where it was."),
)


def fix_hint(message: str) -> str | None:
    """A plain next step for a known refusal, or None."""

    lowered = message.casefold()
    for needle, hint in _FIX_HINTS:
        if needle.casefold() in lowered:
            return hint
    return None


def plain_failure(operation: str, message: str) -> str:
    """The sentence a status line shows for a failed operation."""

    hint = fix_hint(message)
    text = f"Couldn't {operation}: {message.strip()}"
    return f"{text} {hint}" if hint else text


def show_operation_error(parent: QWidget | None, operation: str, message: str,
                         *, source_unchanged: bool = True) -> None:
    """One error dialog shape for every page: plain title, real cause, next step, full text."""

    hint = fix_hint(message)
    lines = [f"Couldn't {operation}."]
    detail = message.strip()
    # The cause is the first line of what the backend said; the rest stays under Details.
    first = detail.splitlines()[0] if detail else ""
    if first:
        lines.append(first)
    lines.append(hint or f"See Details for the error. {DISCORD_HINT}")
    if source_unchanged:
        lines.append("Your original file was not changed.")
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Critical)
    box.setWindowTitle(f"Couldn't {operation}")
    box.setText("\n\n".join(lines))
    if detail:
        box.setDetailedText(detail)
    box.setStandardButtons(QMessageBox.Ok)
    box.exec_()


def suggest_copy_name(source: str | Path, *, suffix: str = "modded") -> str:
    """``{stem} ({suffix}).xiso.iso`` next to ``source``; a numeric suffix when that exists."""

    path = Path(str(source))
    if not str(source).strip():
        return ""
    name = path.name
    for ending in (".xiso.iso", ".xiso", ".iso", ".img"):
        if name.casefold().endswith(ending):
            stem = name[: -len(ending)]
            break
    else:
        stem = path.stem
    stem = stem.strip() or "ESPN NFL 2K5"
    candidate = path.with_name(f"{stem} ({suffix}).xiso.iso")
    counter = 2
    while candidate.exists():
        candidate = path.with_name(f"{stem} ({suffix} {counter}).xiso.iso")
        counter += 1
    return str(candidate)


__all__ = [
    "DISCORD_HINT", "Details", "NOT_TESTED", "XEMU_LINE", "fix_hint", "plain_failure",
    "show_operation_error", "source_captions", "suggest_copy_name", "tab_title", "write_caption",
]
