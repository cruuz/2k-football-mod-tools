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
import re
from string import Template

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QPalette
from PyQt5.QtWidgets import QLabel, QMessageBox, QSizePolicy, QToolButton, QVBoxLayout, QWidget

#: The compatibility line every executable-patch page shows once.
XEMU_LINE = "For xemu; original Xbox support is not provided."

#: The qualifier next to a change nobody has watched in-game yet.
NOT_TESTED = "Not yet tested in-game"

#: Where a lost first-timer should ask.  The Help menu carries the same link.
DISCORD_HINT = "Share that text on the Discord if you need help."


#: Every colour the Build & Share pages paint text on.  The two themes use the
#: same names so a test can compare the same semantic pair in both.  Values are
#: kept as literals because Qt stylesheets cannot read Python tokens.
STUDIO_THEMES = {
    "dark": {
        "canvas": "#0c1220", "surface": "#101827", "surface_alt": "#0d1624",
        "text": "#edf3fc", "muted": "#8e9db2", "subtle": "#a2afc1",
        "disabled_text": "#8b98ad", "disabled_bg": "#141d2a",
        "field_disabled_text": "#8f9db2", "field_disabled_bg": "#121a27",
        "field_bg": "#0d1624", "field_text": "#e5ecf6",
        "selection_bg": "#2b5165", "selection_text": "#ffffff",
        "button_bg": "#1a2940", "button_text": "#dce6f3",
        "primary_bg": "#32d5c6", "primary_text": "#06151b",
        "badge_text": "#f3d27a", "badge_bg": "#2a2a1c", "badge_border": "#6a5a2a",
        "checkbox_disabled": "#9aa7b8", "checkbox_checked": "#d8ffe6",
        "indicator_border": "#8a94a6", "indicator_bg": "#1b1f27", "indicator_checked": "#2ecc71",
        "indicator_disabled_border": "#4a5060", "indicator_disabled_bg": "#22262e",
        "tab_bg": "#131c30", "tab_text": "#9fb2cd",
        "tab_selected_bg": "#0c1220", "tab_selected_text": "#6ee7c7",
        "border": "#253249", "muted_card": "#9aabc0", "muted_card_bg": "#121f31",
        "eyebrow": "#65e4d8", "page_title": "#ffffff", "card_text": "#a2afc1",
        "warning": "#f0c879", "open_bg": "#193b3e", "open_text": "#75e7dc",
        "danger_text": "#f0a0a6", "scroll_handle": "#35465f",
        "tooltip_bg": "#192438", "tooltip_text": "#edf3fc", "tooltip_border": "#3b4d68",
    },
    "light": {
        "canvas": "#f3f6fa", "surface": "#e8eef6", "surface_alt": "#ffffff",
        "text": "#14202e", "muted": "#4a586b", "subtle": "#3f4c5e",
        "disabled_text": "#5b6879", "disabled_bg": "#e7ebf1",
        "field_disabled_text": "#5b6879", "field_disabled_bg": "#eef1f5",
        "field_bg": "#ffffff", "field_text": "#14202e",
        "selection_bg": "#cfe3f7", "selection_text": "#102a43",
        "button_bg": "#e1e8f1", "button_text": "#14202e",
        "primary_bg": "#0b6f63", "primary_text": "#ffffff",
        "badge_text": "#6b4e00", "badge_bg": "#fff1c7", "badge_border": "#d3a93a",
        "checkbox_disabled": "#5b6879", "checkbox_checked": "#0b5f57",
        "indicator_border": "#5b6b7f", "indicator_bg": "#ffffff", "indicator_checked": "#0b6f63",
        "indicator_disabled_border": "#aab4c2", "indicator_disabled_bg": "#e9edf2",
        "tab_bg": "#e4ebf4", "tab_text": "#334155",
        "tab_selected_bg": "#ffffff", "tab_selected_text": "#0b5f57",
        "border": "#c7d2e0", "muted_card": "#334155", "muted_card_bg": "#e8eef6",
        "eyebrow": "#0b6f63", "page_title": "#0b1520", "card_text": "#3f4c5e",
        "warning": "#8a4b00", "open_bg": "#d9f3ef", "open_text": "#075e54",
        "danger_text": "#9b1c2c", "scroll_handle": "#aab8c9",
        "tooltip_bg": "#ffffff", "tooltip_text": "#14202e", "tooltip_border": "#aab8c9",
    },
}

#: Semantic text/background pairs checked by the readability tests.  Body text
#: needs 4.5:1; large text (18 pt, or 14 pt bold) needs 3:1, but none of the
#: pairs below is large, so every one is held to 4.5:1.
THEME_TEXT_PAIRS = (
    ("text", "canvas"),
    ("muted", "canvas"),
    ("subtle", "canvas"),
    ("disabled_text", "disabled_bg"),
    ("field_disabled_text", "field_disabled_bg"),
    ("field_text", "field_bg"),
    ("selection_text", "selection_bg"),
    ("button_text", "button_bg"),
    ("primary_text", "primary_bg"),
    ("badge_text", "badge_bg"),
    ("checkbox_disabled", "canvas"),
    ("checkbox_checked", "canvas"),
    ("tab_text", "tab_bg"),
    ("tab_selected_text", "tab_selected_bg"),
    ("page_title", "canvas"),
    ("card_text", "canvas"),
    ("warning", "muted_card_bg"),
    ("open_text", "open_bg"),
    ("danger_text", "canvas"),
    ("tooltip_text", "tooltip_bg"),
)


def _luminance(colour: str) -> float:
    value = colour.lstrip("#")
    channels = [int(value[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast_ratio(foreground: str, background: str) -> float:
    """WCAG 2.x contrast ratio for two ``#rrggbb`` colours."""

    lighter, darker = sorted((_luminance(foreground), _luminance(background)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def theme_tokens(theme: str) -> dict[str, str]:
    return dict(STUDIO_THEMES.get(theme, STUDIO_THEMES["dark"]))


def studio_palette(theme: str) -> QPalette:
    """The palette for native dialogs and unstyled widgets in one theme."""

    t = theme_tokens(theme)
    result = QPalette()
    roles = {
        QPalette.Window: t["canvas"], QPalette.WindowText: t["text"],
        QPalette.Base: t["field_bg"], QPalette.AlternateBase: t["surface_alt"],
        QPalette.Text: t["field_text"], QPalette.Button: t["button_bg"],
        QPalette.ButtonText: t["button_text"], QPalette.Highlight: t["selection_bg"],
        QPalette.HighlightedText: t["selection_text"], QPalette.ToolTipBase: t["tooltip_bg"],
        QPalette.ToolTipText: t["tooltip_text"], QPalette.Link: t["open_text"],
        QPalette.PlaceholderText: t["muted"],
    }
    for group in (QPalette.Active, QPalette.Inactive):
        for role, colour in roles.items():
            result.setColor(group, role, QColor(colour))
    for role, colour in roles.items():
        result.setColor(QPalette.Disabled, role, QColor(t["disabled_text"]))
    result.setColor(QPalette.Disabled, QPalette.Base, QColor(t["field_disabled_bg"]))
    result.setColor(QPalette.Disabled, QPalette.Button, QColor(t["disabled_bg"]))
    result.setColor(QPalette.Disabled, QPalette.Highlight, QColor(t["selection_bg"]))
    return result


_BUILD_PANEL_QSS = Template("""
    QGroupBox { font-weight: 600; margin-top: 14px; }
    QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }
    QCheckBox { padding: 4px 2px; spacing: 10px; }
    QCheckBox::indicator { width: 20px; height: 20px; border: 2px solid $indicator_border; border-radius: 4px; background: $indicator_bg; }
    QCheckBox::indicator:unchecked:hover { border-color: $text; }
    QCheckBox::indicator:checked { background: $indicator_checked; border-color: $indicator_checked;
        image: url(:/qt-project.org/styles/commonstyle/images/standardbutton-apply-16.png); }
    QCheckBox::indicator:disabled { border-color: $indicator_disabled_border; background: $indicator_disabled_bg; }
    QCheckBox:checked { color: $checkbox_checked; font-weight: 600; }
    QCheckBox:disabled { color: $checkbox_disabled; }
    QCheckBox::indicator:focus { border-color: $primary_bg; }
    QLabel#optionBadge { color: $badge_text; background: $badge_bg; border: 1px solid $badge_border;
        border-radius: 6px; padding: 1px 6px; }
    QPushButton#presetButton { padding: 8px 14px; font-weight: 600; }
""")


def build_panel_stylesheet(theme: str) -> str:
    return _BUILD_PANEL_QSS.safe_substitute(theme_tokens(theme))


_LIGHT_SHELL_QSS = Template("""
    QMainWindow#studioWindow, QWidget { background: $canvas; color: $text; }
    QTabWidget::pane { border: 1px solid $border; background: $canvas; }
    QTabBar::tab { background: $tab_bg; color: $tab_text; border: 1px solid $border; }
    QTabBar::tab:selected { background: $tab_selected_bg; color: $tab_selected_text; border-color: $border; }
    QTabBar::tab:hover:!selected { color: $text; }
    QFrame#sidebar { background: $surface; border-right: 1px solid $border; }
    QFrame#header, QFrame#footer { background: $surface; border-color: $border; }
    QLabel#brandTitle { color: $page_title; }
    QLabel#mutedLabel, QLabel#cardBody, QLabel#heroSubtitle, QLabel#operationStatus { color: $muted; }
    QLabel#pageTitle, QLabel#heroTitle, QLabel#heroTitleSmall, QLabel#cardTitle, QLabel#panelTitle { color: $page_title; }
    QLabel#eyebrow, QLabel#stepNumber { color: $eyebrow; }
    QLabel#safetyCard { color: $muted_card; background: $muted_card_bg; border: 1px solid $border; }
    QLabel#sourcePill { color: $muted; background: $surface_alt; border: 1px solid $border; }
    QLabel#sourcePill[ready="true"] { color: $open_text; }
    QLabel#teamKitWarning { color: $warning; }
    QLabel#countPill, QLabel#editCount { color: $muted; background: $surface_alt; }
    QLabel#findingsBanner, QLabel#findingsNote { color: $muted_card; background: $muted_card_bg; }
    QLabel#codeLabel { color: $muted; background: $surface_alt; }
    QListWidget#navigation::item { color: $tab_text; }
    QListWidget#navigation::item:hover { background: $tab_bg; color: $text; }
    QListWidget#navigation::item:selected { background: $selection_bg; color: $tab_selected_text; }
    QListWidget#navigation:focus { border-color: $primary_bg; }
    QFrame#stepCard, QFrame#capabilityCard, QFrame#panel, QFrame#callout, QFrame#teamKitBar {
        background: $surface_alt; border: 1px solid $border;
    }
    QPushButton { background: $button_bg; color: $button_text; border: 1px solid $border; }
    QPushButton:hover:!disabled { background: $selection_bg; border-color: $primary_bg; color: $text; }
    QPushButton:pressed:!disabled { background: $surface; }
    QPushButton:focus { border: 2px solid $primary_bg; }
    QPushButton#primaryButton, QPushButton#buildButton { background: $primary_bg; color: $primary_text; border-color: $primary_bg; }
    QPushButton#primaryButton:hover:!disabled, QPushButton#buildButton:hover:!disabled {
        background: $open_text; border-color: $open_text; color: $primary_text;
    }
    QPushButton#openSourceButton { background: $open_bg; color: $open_text; border-color: $open_text; }
    QPushButton#openSourceButton:hover:!disabled { background: $open_bg; border-color: $primary_bg; }
    QPushButton#dangerQuietButton { background: transparent; color: $danger_text; border-color: $danger_text; }
    QPushButton:disabled, QPushButton#primaryButton:disabled, QPushButton#openSourceButton:disabled,
    QPushButton#dangerQuietButton:disabled, QPushButton#buildButton:disabled, QPushButton#launchButton:disabled {
        background: $disabled_bg; color: $disabled_text; border: 1px solid $border;
    }
    QPushButton#launchButton { background: $surface_alt; color: $muted; border-color: $border; }
    QPushButton#launchButton:hover:!disabled { background: $open_bg; color: $open_text; border-color: $open_text; }
    QLineEdit, QComboBox { background: $field_bg; color: $field_text; border: 1px solid $border;
        selection-background-color: $selection_bg; selection-color: $selection_text; }
    QLineEdit:hover, QComboBox:hover { border-color: $indicator_border; }
    QLineEdit:focus, QComboBox:focus { border-color: $primary_bg; }
    QLineEdit:disabled, QComboBox:disabled { background: $field_disabled_bg; color: $field_disabled_text; border-color: $border; }
    QComboBox QAbstractItemView { background: $field_bg; color: $field_text; selection-background-color: $selection_bg;
        selection-color: $selection_text; border: 1px solid $border; }
    QPlainTextEdit, QTextEdit { background: $field_bg; color: $field_text; border: 1px solid $border; }
    QListWidget#assetList, QTreeWidget#componentTree { background: $field_bg; color: $field_text; border: 1px solid $border; }
    QListWidget#assetList::item:hover, QTreeWidget#componentTree::item:hover { background: $tab_bg; color: $text; }
    QListWidget#assetList::item:selected, QTreeWidget#componentTree::item:selected {
        background: $selection_bg; color: $selection_text;
    }
    QListWidget#assetList:disabled { color: $disabled_text; }
    QHeaderView::section { background: $surface; color: $text; border: 1px solid $border; }
    QLabel#previewImage { background: $surface_alt; border: 1px solid $border; }
    QFrame#pngPreview { background: $surface_alt; border: 1px solid $border; }
    QScrollArea { background: transparent; }
    QProgressBar { background: $disabled_bg; }
    QProgressBar::chunk { background: $primary_bg; }
    QScrollBar:vertical { background: $surface; }
    QScrollBar:horizontal { background: $surface; }
    QScrollBar::handle:vertical { background: $scroll_handle; }
    QScrollBar::handle:horizontal { background: $scroll_handle; }
    QScrollBar::handle:vertical:hover { background: $indicator_border; }
    QScrollBar::handle:horizontal:hover { background: $indicator_border; }
    QListWidget#navigation QScrollBar:vertical { background: $surface; }
    QListWidget#navigation QScrollBar::handle:vertical { background: $scroll_handle; }
    QToolTip { background: $tooltip_bg; color: $tooltip_text; border: 1px solid $tooltip_border; }
""")


def light_shell_stylesheet() -> str:
    """Colour overrides appended after the dark shell sheet for the light theme."""

    return _LIGHT_SHELL_QSS.safe_substitute(theme_tokens("light"))


class WrappedLabel(QLabel):
    """A word-wrapped label that reserves the height its full text needs.

    A QScrollArea sizes a page to the page's minimum size.  A plain wrapped
    QLabel reports a one-line minimum, so long descriptions were cut off and
    could only be read from their tooltip.  This label folds the wrapped height
    into its size hints and refreshes them when the width changes.
    """

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setWordWrap(True)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)

    def _wrapped_height(self, width: int) -> int:
        margins = self.contentsMargins()
        indent = max(0, self.indent())
        available = max(1, width - margins.left() - margins.right() - indent)
        rect = self.fontMetrics().boundingRect(
            0, 0, available, 1_000_000, int(Qt.TextWordWrap), self.text()
        )
        return rect.height() + margins.top() + margins.bottom()

    def minimumSizeHint(self):  # type: ignore[override]
        hint = super().minimumSizeHint()
        if self.wordWrap() and self.width() > 0 and self.text():
            hint.setHeight(self._wrapped_height(self.width()))
        return hint

    def sizeHint(self):  # type: ignore[override]
        hint = super().sizeHint()
        if self.wordWrap() and self.width() > 0 and self.text():
            hint.setHeight(max(hint.height(), self._wrapped_height(self.width())))
        return hint

    def resizeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().resizeEvent(event)
        self.updateGeometry()

    def setText(self, text: str) -> None:  # type: ignore[override]
        super().setText(text)
        self.updateGeometry()


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


def disc_next_steps(target: str | Path) -> str:
    """Name the completed image and the roster/save steps shared by both builders."""
    return (f"Next: in xemu, choose Machine > Load Disc and open {target}, "
            "or click Play latest disc in xemu in Studio.\n"
            "In the game, load the disc roster, then start a fresh franchise. "
            "An existing franchise keeps its saved roster. For SOFTDRINK, set xemu System Memory to 128 MiB.")


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

        label = WrappedLabel(text)
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
    # Opening a disc fills the Studio's own private game copy, which lives in the user's
    # profile, not beside the disc image. The message names the folder and its drive.
    ("private copy of the game's art", "Fix: free up room on the drive named above, then open the disc again."),
    ("already exists", "Fix: choose a new filename."),
    ("must not be the source", "Fix: choose a different output file."),
    ("target must not be the source", "Fix: choose a different output file."),
    ("neither retail nor this patch", "Fix: start from a disc this patch recognises, or turn that change off."),
    ("free space", "Fix: free up room where the copy is being written, or choose another folder."),
    # The operating system's own words when a drive fills mid-write (POSIX errno 28 and
    # Windows ERROR_DISK_FULL). They name no drive, so say which one to look at.
    ("No space left on device",
     "Fix: a drive is full. Free up room on the drive you are writing to, and on the drive that holds your user profile "
     "(C: on Windows), where the Studio keeps its private game copy, then try again."),
    ("not enough space on the disk",
     "Fix: a drive is full. Free up room on the drive you are writing to, and on the drive that holds your user profile "
     "(C: on Windows), where the Studio keeps its private game copy, then try again."),
    ("inside OneDrive", "Fix: choose a folder OneDrive does not sync, such as a new folder directly on your C: drive."),
    # The Studio's own .studio-build-* folder is named for the user by what the
    # file in it was for, never by its random temporary path, so the hint is
    # about the build rather than about a file they could go and look for.
    ("private copy of the disc", "Fix: build again. If it happens twice, copy this message and share it on the Discord."),
    ("Permission denied", "Fix: choose a folder you can write to."),
    ("not a regular file", "Fix: choose the disc file itself."),
    ("no longer on this computer", "Fix: open the file you want to build from, then build again."),
    ("No such file", "Fix: check that the file is still where it was."),
    # Windows words a missing file its own way, so the POSIX needle above never
    # matched there and a renamed build copy reached a tester with no next step
    # at all: "[WinError 2] The system cannot find the file specified".
    ("cannot find the file", "Fix: check that the file is still where it was."),
    ("cannot find the path", "Fix: check that the folder is still where it was."),
)


def fix_hint(message: str) -> str | None:
    """A plain next step for a known refusal, or None."""

    lowered = message.casefold()
    for needle, hint in _FIX_HINTS:
        if needle.casefold() in lowered:
            return hint
    return None


# These patterns recognize diagnostics coming from workers, never product copy.
_CLASS_PREFIX = re.compile(r"\b(?:[A-Za-z_][A-Za-z0-9_.]*)?(?:Error|Exception):\s*")
_PHASE_LINE = re.compile(r"(?:NFL2K5_)?BUILD" r"_PHASE\b[^\n]*")


def plain_error(message: object) -> str:
    """Keep the actual cause, excluding worker class names and progress records."""
    text = str(message).strip()
    text = _PHASE_LINE.sub("", text)
    if "Traceback (most recent call last):" in text:
        lines = text.splitlines()
        causes = [i for i, line in enumerate(lines) if _CLASS_PREFIX.match(line)]
        if causes:
            text = "\n".join(lines[causes[-1]:])
    text = _CLASS_PREFIX.sub("", text)
    return text.strip() or "The operation stopped without an explanation."


def failure_body(message: object, *, hint: str | None = None,
                 source_unchanged: bool = True) -> str:
    """A cause, a useful next step, and a narrowly scoped source assurance."""
    cause = plain_error(message)
    step = hint or fix_hint(cause)
    if not step:
        step = "Review the selected file and options, then try again. If it still fails, copy this message and share it on the Discord."
    lines = [cause, step]
    if source_unchanged and "Your original game disc was not changed." not in cause:
        lines.append("Your original game disc was not changed.")
    return "\n\n".join(lines)


def plain_failure(operation: str, message: str) -> str:
    """The sentence a status line shows for a failed operation."""

    message = plain_error(message)
    hint = fix_hint(message)
    text = f"Couldn't {operation}: {message}"
    return f"{text} {hint}" if hint else text


def show_operation_error(parent: QWidget | None, operation: str, message: str,
                         *, source_unchanged: bool = True) -> None:
    """One error dialog shape for every page: plain title, real cause, next step, full text."""

    # Every caught failure the user sees also lands in errors.log with the
    # Studio version, so a report can be a file rather than a phone photo.
    # Logging must never be the reason a dialog fails to appear.
    try:
        from mod_editor.gui import crash_report
        crash_report.record_operation(operation, message, "2K5 Mod Studio")
    except Exception:  # noqa: BLE001
        pass
    hint = fix_hint(message)
    lines = [f"Couldn't {operation}."]
    detail = plain_error(message)
    # The cause is the first line of what the backend said; the rest stays under Details.
    first = detail.splitlines()[0] if detail else ""
    if first:
        lines.append(first)
    lines.append(hint or f"Review the selected file and options, then try again. {DISCORD_HINT}")
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
    "plain_error", "failure_body", "show_operation_error", "source_captions", "suggest_copy_name", "tab_title", "write_caption", "disc_next_steps",
]
