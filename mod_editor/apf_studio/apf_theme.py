"""APF Studio's application theme and shared widget behaviour.

Palette tokens are the only UI colours: canvas (window), surface (panels),
raised (controls), base/alternate (data rows), border, text/muted, accent/ink
(primary action), selection, success/info/warning/danger. Text, including
disabled text, must contrast at least 4.5:1 with its surface. Artwork palettes
and game colour swatches are data, not theme tokens.

Install once on QApplication, before constructing pages. This covers native
Qt dialogs, parentless authoring dialogs, menus, combo popups and file choosers
as well as the main window. Do not add local dialog stylesheets.
"""
from __future__ import annotations

import html
import re
from pathlib import Path
import tempfile

from PyQt5.QtCore import QEvent, QObject, Qt
from PyQt5.QtGui import QColor, QFont, QPalette, QPainter, QTextDocument
from PyQt5.QtWidgets import (
    QAbstractItemView, QApplication, QBoxLayout, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QHeaderView, QLabel, QLayout, QMessageBox, QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
    QLineEdit, QStyledItemDelegate, QStyle, QStyleOption, QTableView, QTableWidget, QToolTip,
)

TOKENS = {
    "canvas": "#0d1420", "surface": "#141f2f", "raised": "#203149",
    "base": "#101a29", "alternate": "#182638", "border": "#40536c",
    "text": "#edf3fc", "muted": "#b6c5d9", "accent": "#ffad73",
    "ink": "#17110c", "selection": "#304e70", "success": "#77e3b0",
    "info": "#a5c9ff", "warning": "#ffce7a", "danger": "#ffabb3",
}


def color(token):
    return TOKENS[token]


def status_style(token):
    return f"color: {color(token)}; border-color: {color(token)};"


def contrast(foreground, background):
    """WCAG sRGB contrast; also used by the effective-palette UI audit."""
    def luminance(value):
        rgb = QColor(value).getRgbF()[:3]
        values = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in rgb]
        return sum(a * b for a, b in zip(values, (.2126, .7152, .0722)))
    a, b = sorted((luminance(foreground), luminance(background)))
    return (b + .05) / (a + .05)


def palette():
    result = QPalette()
    roles = {
        QPalette.Window: "canvas", QPalette.WindowText: "text", QPalette.Base: "base",
        QPalette.AlternateBase: "alternate", QPalette.Text: "text", QPalette.Button: "raised",
        QPalette.ButtonText: "text", QPalette.Highlight: "selection", QPalette.HighlightedText: "text",
        QPalette.ToolTipBase: "raised", QPalette.ToolTipText: "text", QPalette.Link: "info",
        QPalette.Light: "border", QPalette.Mid: "border", QPalette.Dark: "canvas",
        QPalette.BrightText: "text", QPalette.PlaceholderText: "muted",
    }
    for group in (QPalette.Active, QPalette.Inactive, QPalette.Disabled):
        for role, token in roles.items():
            result.setColor(group, role, QColor(color(token)))
    return result


def stylesheet(icons=None):
    # Tokens use $name so Qt's braces remain readable and copyable.
    sheet = """
    QWidget { color: $text; font-size: 12px; }
    QMainWindow, QDialog, QMessageBox, QStackedWidget, QWidget#workspace { background: $canvas; }
    QLabel { background: transparent; }
    QFrame#sidebar, QFrame#header, QFrame#footer { background: $surface; }
    QFrame#sidebar { border-right: 1px solid $border; }
    QFrame#header { border-bottom: 1px solid $border; }
    QFrame#footer { border-top: 1px solid $border; }
    QLabel#brandMark { background: $accent; color: $ink; border-radius: 8px; padding: 8px;
                           font-size: 18px; font-weight: bold; }
    QLabel#brandTitle, QLabel#pageTitle, QLabel#panelTitle, QLabel#cardTitle { font-weight: bold; }
    QLabel#pageTitle { font-size: 22px; }
    QLabel#panelTitle, QLabel#cardTitle { font-size: 14px; }
    QLabel#heroTitle { font-size: 28px; font-weight: bold; }
    QLabel#heroTitleSmall { font-size: 22px; font-weight: bold; }
    QLabel#eyebrow, QLabel#stepNumber { color: $accent; font-weight: bold; }
    QLabel#eyebrow { font-size: 10px; }
    QLabel#mutedLabel, QLabel#pageSummary, QLabel#heroSubtitle, QLabel#metadataText,
    QLabel#cardBody, QLabel#capabilitySummary, QLabel#filterLabel { color: $muted; }
    QLabel#sourcePill, QLabel#statusBadge, QLabel#specPill, QLabel#countPill, QLabel#editCount {
        color: $muted; background: $raised; border-radius: 6px; padding: 4px 7px;
    }
    QLabel#sourcePill[ready="true"] { color: $success; }
    QLabel#safetyCard, QLabel#findingText, QLabel#contractText {
        color: $muted; background: $base; border-radius: 6px; padding: 6px 8px;
    }
    QLabel#safetyCard { font-size: 11px; }
    QLabel#validationBanner { padding: 9px; border-radius: 6px; color: $warning;
                              background: $raised; border-left: 3px solid $warning; }
    QLabel#validationBanner[valid="true"] { color: $success; border-color: $success; }
    QFrame#panel, QFrame#stepCard, QFrame#capabilityCard, QFrame#callout,
    QFrame#baseRatingsPanel, QFrame#audioAnnotationCard, QFrame#reserveEditor {
        background: $surface; border: 1px solid $border; border-radius: 8px;
    }
    QFrame#capabilityPanel { background: $surface; border-radius: 6px; }
    QFrame#inspectorDetail, QFrame#emptyState { background: $base; border-radius: 6px; }
    QPushButton, QToolButton { background: $raised; color: $text; border: 1px solid $border;
        border-radius: 6px; padding: 4px 10px; min-height: 24px; font-weight: bold; }
    QPushButton:hover, QToolButton:hover { background: $selection; }
    QPushButton#primaryButton, QToolButton#primaryButton, QPushButton#buildButton,
    QDialogButtonBox QPushButton:default { background: $accent; color: $ink; border: 1px solid $accent; }
    QPushButton#utilityButton, QToolButton#utilityButton { background: $surface; color: $muted; }
    QPushButton#dangerQuietButton { color: $danger; background: $surface; }
    QPushButton#launchButton { color: $success; }
    QPushButton:disabled, QToolButton:disabled, QPushButton#primaryButton:disabled,
    QToolButton#primaryButton:disabled, QPushButton#buildButton:disabled,
    QPushButton#launchButton:disabled, QPushButton#dangerQuietButton:disabled,
    QDialogButtonBox QPushButton:disabled { background: $surface; color: $muted; border-color: $border; }
    QPushButton:focus, QToolButton:focus { border: 2px solid $accent; }
    QToolButton#clearSearchButton { padding: 2px 7px; }
    QToolButton::menu-indicator { subcontrol-position: center right; right: 5px; }
    QToolButton#primaryButton { padding-right: 20px; }
    QDialogButtonBox { background: transparent; padding-top: 6px; }
    QDialogButtonBox QPushButton { min-width: 76px; }
    QLineEdit, QAbstractSpinBox, QTextEdit, QPlainTextEdit, QComboBox {
        background: $base; color: $text; border: 1px solid $border; border-radius: 5px;
        padding: 4px 7px; selection-background-color: $selection; selection-color: $text;
    }
    QLineEdit, QComboBox, QAbstractSpinBox { min-height: 24px; }
    QLineEdit:disabled, QComboBox:disabled, QAbstractSpinBox:disabled { color: $muted; background: $surface; }
    QLineEdit:focus, QComboBox:focus, QAbstractSpinBox:focus, QTextEdit:focus,
    QPlainTextEdit:focus, QAbstractItemView:focus { border: 1px solid $accent; }
    QAbstractSpinBox { padding-right: 20px; }
    QAbstractSpinBox::up-button, QAbstractSpinBox::down-button { width: 18px; background: $raised; }
    QComboBox { padding-right: 24px; }
    QComboBox::drop-down { width: 22px; border: none; }
    QComboBox::down-arrow { image: url("$down"); width: 12px; height: 12px; }
    QAbstractSpinBox::up-arrow { image: url("$up"); width: 10px; height: 10px; }
    QAbstractSpinBox::down-arrow { image: url("$down"); width: 10px; height: 10px; }
    QComboBox QAbstractItemView { background: $raised; color: $text; selection-background-color: $selection;
                                selection-color: $text; border: 1px solid $border; }
    QAbstractItemView { background: $base; alternate-background-color: $alternate; color: $text;
        border: 1px solid $border; border-radius: 5px; selection-background-color: $selection;
        selection-color: $text; gridline-color: $border; outline: none; }
    QAbstractItemView::item { padding: 4px; color: $text; }
    QAbstractItemView::item:selected { background: $selection; color: $text; }
    QAbstractItemView::item:disabled { color: $muted; }
    QHeaderView { background: $surface; color: $text; }
    QHeaderView::section, QTableCornerButton::section { background: $raised; color: $text;
        border: none; border-bottom: 1px solid $border; padding: 6px; font-weight: bold; }
    QListWidget#navigation { background: transparent; border: none; }
    QListWidget#navigation::item { color: $muted; padding: 6px 9px; border-radius: 5px; }
    QListWidget#navigation::item:selected { background: $selection; color: $text; border-left: 3px solid $accent; }
    QListWidget#navigation::item:hover { background: $raised; }
    QTabWidget::pane { background: $surface; border: 1px solid $border; border-radius: 6px; }
    QTabBar::tab { background: $surface; color: $muted; padding: 7px 10px;
                  border-bottom: 2px solid transparent; margin-right: 2px; }
    QTabBar::tab:selected { background: $raised; color: $text; border-color: $accent; }
    QTabBar::tab:disabled { color: $muted; }
    QTabBar::scroller { width: 40px; }
    QCheckBox, QRadioButton { spacing: 7px; background: transparent; color: $text; }
    QCheckBox:disabled, QRadioButton:disabled { color: $muted; }
    QCheckBox::indicator, QRadioButton::indicator { width: 15px; height: 15px;
        background: $base; border: 1px solid $muted; border-radius: 3px; }
    QRadioButton::indicator { border-radius: 8px; }
    QCheckBox::indicator:checked, QRadioButton::indicator:checked { background: $accent; border: 2px solid $ink; }
    QCheckBox::indicator:checked { image: url("$check"); }
    QCheckBox::indicator:indeterminate { background: $info; }
    QGroupBox { border: 1px solid $border; border-radius: 6px; margin-top: 12px; padding-top: 10px; }
    QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; color: $text; }
    QMenuBar, QMenu { background: $surface; color: $text; }
    QMenu::item { padding: 7px 22px; }
    QMenu::item:selected, QMenuBar::item:selected { background: $selection; color: $text; }
    QMenu::item:disabled { color: $muted; }
    QMenu::separator { height: 1px; background: $border; margin: 5px; }
    QLabel#imagePreview { color: $muted; border: 1px dashed $border; border-radius: 6px; padding: 6px; }
    QLabel#imagePreview[previewState="error"] { color: $danger; }
    QFrame#audioReplacementDropZone { background: $surface; border: 1px dashed $border; border-radius: 6px; }
    QProgressBar { background: $raised; color: $text; border: none; border-radius: 3px; text-align: center; }
    QProgressBar::chunk { background: $selection; border-radius: 3px; }
    QSplitter::handle { background: $border; }
    QSplitter::handle:horizontal { width: 4px; }
    QSplitter::handle:vertical { height: 4px; }
    QScrollArea { background: $canvas; border: none; }
    QScrollBar:vertical { background: $surface; width: 10px; margin: 0; }
    QScrollBar:horizontal { background: $surface; height: 10px; margin: 0; }
    QScrollBar::handle { background: $border; border-radius: 4px; min-height: 24px; min-width: 24px; }
    QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
    QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
    QToolTip { color: $text; background: $raised; border: 1px solid $border; padding: 7px; }
    """
    substitutions = dict(TOKENS, **(icons or {"up": "", "down": "", "check": ""}))
    return re.sub(r"\$(\w+)", lambda m: substitutions[m[1]], sheet)


class FullTextDelegate(QStyledItemDelegate):
    """Elide visually, expose the complete cell through a literal tooltip."""
    def helpEvent(self, event, view, option, index):
        if event.type() == QEvent.ToolTip and index.isValid():
            value = index.data(Qt.ToolTipRole) or index.data(Qt.DisplayRole)
            if value is not None:
                QToolTip.showText(event.globalPos(), "<qt>" + html.escape(str(value)) + "</qt>", view)
                return True
        return super().helpEvent(event, view, option, index)


class CompactLabel(QLabel):
    """Keep full accessible text while eliding secondary prose to two lines."""
    def paintEvent(self, event):
        if not (self.property("apfCompact") or
                self.objectName() in ("findingText", "contractText", "metadataText", "mutedLabel", "pageSummary")
                and len(self.text()) > 160):
            return super().paintEvent(event)
        text = self.text()
        if self.textFormat() == Qt.RichText or text.startswith("<"):
            document = QTextDocument()
            document.setHtml(text)
            text = document.toPlainText()
        self.setToolTip(self.text())
        painter = QPainter(self)
        option = QStyleOption()
        option.initFrom(self)
        self.style().drawPrimitive(QStyle.PE_Widget, option, painter, self)
        rect = self.contentsRect().adjusted(8, 3, -8, -3)
        metrics = self.fontMetrics()
        words = text.split()
        lines = []
        count = max(1, min(2, rect.height() // metrics.lineSpacing()))
        for line in range(count):
            if line == count - 1:
                lines.append(metrics.elidedText(" ".join(words), Qt.ElideRight, rect.width()))
                break
            taken = []
            while words and metrics.horizontalAdvance(" ".join(taken + words[:1])) <= rect.width():
                taken.append(words.pop(0))
            lines.append(" ".join(taken))
        painter.setPen(self.palette().color(QPalette.WindowText))
        for line, text in enumerate(lines):
            painter.drawText(rect.x(), rect.y() + metrics.ascent() + line * metrics.lineSpacing(), text)
        painter.end()


def sort_visual_rows(table, column, order):
    """Sort visual sections without changing logical row/record identities.

    Older editors use currentRow() as an index into their parsed record list.
    QTableWidget.sortItems would silently retarget those edits. Moving vertical
    header sections orders the presentation and its cell widgets while keeping
    every logical index and selection bound to the same record.
    """
    header = table.verticalHeader()
    def key(row):
        item = table.item(row, column)
        widget = table.cellWidget(row, column)
        value = item.text() if item else widget.currentText() if isinstance(widget, QComboBox) else ""
        return [(0, int(part)) if part.isdigit() else (1, part.casefold())
                for part in re.split(r"(\d+)", value)]
    rows = sorted(range(table.rowCount()), key=key, reverse=order == Qt.DescendingOrder)
    for visual, logical in enumerate(rows):
        header.moveSection(header.visualIndex(logical), visual)
    table.horizontalHeader().setSortIndicator(column, order)


def configure_table(table):
    if table.property("apfTable"):
        return
    table.setProperty("apfTable", True)
    table.setAlternatingRowColors(True)
    table.setWordWrap(False)
    table.setTextElideMode(Qt.ElideRight)
    table.setItemDelegate(FullTextDelegate(table))
    table.verticalHeader().setDefaultSectionSize(34)
    header = table.horizontalHeader()
    header.setMinimumSectionSize(48)
    header.setMaximumSectionSize(440)
    header.setDefaultSectionSize(160)
    if isinstance(table, QTableWidget) and not table.isSortingEnabled():
        header.setSectionsClickable(True)
        header.setSortIndicatorShown(True)
        header.setSortIndicator(-1, Qt.AscendingOrder)
        def clicked(column):
            order = Qt.DescendingOrder if header.sortIndicatorSection() == column and header.sortIndicatorOrder() == Qt.AscendingOrder else Qt.AscendingOrder
            sort_visual_rows(table, column, order)
        header.sectionClicked.connect(clicked)


def fit_dialog(dialog):
    """Keep the full frame on the screen containing the parent window."""
    screen = dialog.parentWidget().screen() if dialog.parentWidget() else dialog.screen()
    if screen is None:
        return
    available = screen.availableGeometry().adjusted(16, 32, -16, -16)
    if not dialog.property("apfDialogFitted") and not isinstance(dialog, (QFileDialog, QMessageBox)):
        dialog.setProperty("apfDialogFitted", True)
        original = QWidget.layout(dialog)
        if original is not None:
            original.setSizeConstraint(QLayout.SetNoConstraint)
            for label in dialog.findChildren(QLabel):
                if len(label.text()) > 80:
                    label.setWordWrap(True)
                    label.setMinimumWidth(0)
                    label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
            if (isinstance(original, QBoxLayout) and original.direction() == QBoxLayout.LeftToRight
                    and original.minimumSize().width() > available.width()):
                original.setDirection(QBoxLayout.TopToBottom)
            if original.totalMinimumSize().height() > available.height() or original.totalSizeHint().height() > available.height():
                buttons = dialog.findChildren(QDialogButtonBox)
                content = QWidget()
                content.setLayout(original)
                outer = QVBoxLayout(dialog)
                outer.setContentsMargins(10, 10, 10, 10)
                scroll = QScrollArea()
                scroll.setObjectName("dialogContentScroll")
                scroll.setWidgetResizable(True)
                scroll.setWidget(content)
                outer.addWidget(scroll, 1)
                for button_box in buttons:
                    button_box.setParent(dialog)
                    outer.addWidget(button_box)
                dialog.setMinimumSize(0, 0)
                outer.setSizeConstraint(QLayout.SetNoConstraint)
    dialog.setMinimumSize(0, 0)
    dialog.setMaximumSize(available.size())
    dialog.resize(min(dialog.width(), available.width()), min(dialog.height(), available.height()))
    frame = dialog.frameGeometry()
    frame.moveCenter(available.center())
    dialog.move(max(available.left(), frame.left()), max(available.top(), frame.top()))


class _ThemeEvents(QObject):
    def eventFilter(self, watched, event):
        if event.type() == QEvent.Polish:
            if isinstance(watched, QTableView):
                configure_table(watched)
            elif isinstance(watched, QComboBox):
                watched.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
                watched.setMinimumContentsLength(8)
            elif isinstance(watched, QLabel) and len(watched.text()) > 100 and not watched.toolTip():
                watched.setToolTip(watched.text())
        elif event.type() == QEvent.Show and isinstance(watched, QDialog):
            fit_dialog(watched)
        elif event.type() == QEvent.KeyPress and isinstance(watched, QLineEdit):
            if event.key() == Qt.Key_Escape and (watched.property("studioSearch") or
                    watched.placeholderText().casefold().startswith(("search", "filter"))):
                watched.clear()
                return True
        return False


def install_theme(app=None):
    app = app or QApplication.instance()
    if app is None:
        return
    if getattr(app, "_apf_theme_events", None):
        return
    if not getattr(app, "_apf_theme_events", None):
        app.setStyle("Fusion")
        app.setFont(QFont("DejaVu Sans", 9))
        app._apf_theme_events = _ThemeEvents(app)
        app.installEventFilter(app._apf_theme_events)
        # Qt QSS does not accept inline SVG data URLs. These tiny application
        # glyphs are generated from palette tokens in a private temporary dir.
        app._apf_theme_glyphs = tempfile.TemporaryDirectory(prefix="apf-theme-")
        app._apf_theme_icon_paths = {}
        for name, points, token in (("down", "3,5 8,10 13,5", "text"),
                                    ("up", "3,10 8,5 13,10", "text"),
                                    ("check", "3,8 6,11 13,4", "ink")):
            path = Path(app._apf_theme_glyphs.name) / f"{name}.svg"
            path.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16">'
                            f'<polyline points="{points}" fill="none" stroke="{color(token)}" stroke-width="2"/></svg>',
                            encoding="utf-8")
            app._apf_theme_icon_paths[name] = path.as_posix()
    app.setPalette(palette())
    app.setStyleSheet(stylesheet(app._apf_theme_icon_paths))
