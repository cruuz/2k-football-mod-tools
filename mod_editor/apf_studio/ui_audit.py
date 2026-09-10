"""Offscreen audits of rendered widget palettes and workspace bounds."""
from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPalette
from PyQt5.QtWidgets import (
    QAbstractButton, QAbstractItemView, QAbstractSpinBox, QComboBox, QHeaderView,
    QLabel, QLineEdit, QPlainTextEdit, QTextEdit, QWidget,
)

from .apf_theme import contrast


def contrast_failures(root):
    failures = []
    for widget in (root, *root.findChildren(QWidget)):
        widget.ensurePolished()
        palette = QWidget.palette(widget)
        label = f"{type(widget).__name__}#{widget.objectName()}"
        pairs = []
        if isinstance(widget, QAbstractItemView):
            pairs.extend(((QPalette.Text, QPalette.Base), (QPalette.Text, QPalette.AlternateBase),
                          (QPalette.HighlightedText, QPalette.Highlight)))
        elif isinstance(widget, (QLineEdit, QAbstractSpinBox, QComboBox, QTextEdit, QPlainTextEdit)):
            pairs.append((QPalette.Text, QPalette.Base))
        elif isinstance(widget, QAbstractButton):
            pairs.append((QPalette.ButtonText, QPalette.Button))
        elif isinstance(widget, QLabel) and widget.text().strip():
            pairs.append((QPalette.WindowText, QPalette.Window))
        for foreground, background in pairs:
            for group in (QPalette.Active, QPalette.Inactive, QPalette.Disabled):
                fg, bg = palette.color(group, foreground), palette.color(group, background)
                ratio = contrast(fg, bg)
                if ratio < 4.5:
                    failures.append(f"{label}: {fg.name()} on {bg.name()} = {ratio:.2f}:1 (group {group})")
        if isinstance(widget, QAbstractItemView) and not isinstance(widget, QHeaderView):
            model = widget.model()
            if model is None:
                continue
            # Sample each populated cell; explicit item brushes override QSS.
            for row in range(model.rowCount()):
                try:
                    columns = model.columnCount()
                except TypeError:  # QAbstractListModel hides its C++ columnCount override.
                    columns = 1
                for column in range(columns):
                    index = model.index(row, column)
                    foreground, background = index.data(Qt.ForegroundRole), index.data(Qt.BackgroundRole)
                    fg = foreground.color() if foreground is not None and foreground.style() != Qt.NoBrush else palette.color(QPalette.Text)
                    bg = background.color() if background is not None and background.style() != Qt.NoBrush else palette.color(QPalette.AlternateBase if row % 2 and widget.alternatingRowColors() else QPalette.Base)
                    ratio = contrast(fg, bg)
                    if ratio < 4.5:
                        failures.append(f"{label} cell {row},{column}: {fg.name()} on {bg.name()} = {ratio:.2f}:1")
    return sorted(set(failures))


def page_layout_failures(window):
    """Allow intentional vertical scrolling; refuse horizontal page overflow."""
    host = window.pages.currentWidget()
    page = host.widget()
    failures = []
    if page.width() > host.viewport().width():
        failures.append(f"Page {page.width()}px exceeds viewport {host.viewport().width()}px")
    if host.footer.geometry().bottom() >= host.height() or host.footer.height() < 40:
        failures.append("Workspace actions leave the visible page")
    for widget in page.findChildren(QWidget):
        if not widget.isVisibleTo(page) or QWidget.window(widget) is not window or isinstance(widget, QHeaderView):
            continue
        if isinstance(widget, (QAbstractButton, QAbstractItemView, QLabel, QLineEdit, QComboBox, QAbstractSpinBox)):
            if widget.width() > host.viewport().width():
                failures.append(f"{type(widget).__name__}#{widget.objectName()} is {widget.width()}px wide")
    return failures
