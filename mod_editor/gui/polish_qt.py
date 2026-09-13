"""Small shared accessibility defaults for the two studio shells.

Specific page help always wins. These defaults expose existing labels and help
on keyboard controls too, and keep text buttons readable inside scrolling pages.
"""
from __future__ import annotations
from PyQt5.QtWidgets import (
    QAbstractButton, QAbstractSpinBox, QCheckBox, QComboBox, QFormLayout,
    QGridLayout, QLabel, QLineEdit, QPushButton, QToolButton, QTabWidget, QWidget,
)

def _field_label(widget: QWidget) -> str:
    if widget.accessibleName():
        return widget.accessibleName()
    parent = widget.parentWidget()
    if parent is None:
        return ''
    for label in parent.findChildren(QLabel):
        if label.buddy() is widget:
            return label.text().rstrip(':')
    layout = parent.layout()
    if isinstance(layout, QFormLayout):
        label = layout.labelForField(widget)
        if isinstance(label, QLabel):
            return label.text().rstrip(':')
    if isinstance(layout, QGridLayout):
        index = layout.indexOf(widget)
        if index >= 0:
            row, col, _, _ = layout.getItemPosition(index)
            previous = layout.itemAtPosition(row, col - 1) if col else None
            if previous and isinstance(previous.widget(), QLabel):
                return previous.widget().text().rstrip(':')
    return ''

def polish_controls(root: QWidget) -> None:
    """Copy existing explanations to tooltips; keep full button and tab captions."""
    for widget in (root, *root.findChildren(QWidget)):
        if isinstance(widget, QTabWidget):
            widget.setUsesScrollButtons(True)
            for i in range(widget.count()):
                if not widget.tabToolTip(i):
                    widget.setTabToolTip(i, widget.tabText(i).replace('&&', '&'))
        if isinstance(widget, (QPushButton, QToolButton)) and widget.text():
            # Pages have scrolling hosts. A long action stays reachable instead
            # of losing its last words when Qt divides a narrow horizontal row.
            width = widget.sizeHint().width()
            if widget.maximumWidth() >= width:
                widget.setMinimumWidth(max(widget.minimumWidth(), width))
        if widget.toolTip() or widget.whatsThis():
            continue
        help_text = widget.accessibleDescription()
        label = _field_label(widget)
        if not help_text and isinstance(widget, QCheckBox):
            help_text = f"Turn {widget.text().replace('&&', '&')} on or off."
        elif not help_text and isinstance(widget, QAbstractButton) and widget.text():
            help_text = widget.text().replace('&&', '&').rstrip('…') + '.'
        elif not help_text and isinstance(widget, QComboBox):
            help_text = f'Choose {label}.' if label else 'Choose a value from this list for the current page.'
        elif not help_text and isinstance(widget, QAbstractSpinBox):
            help_text = f'Set {label}.' if label else 'Set the value shown beside this control.'
            if hasattr(widget, 'minimum') and hasattr(widget, 'maximum'):
                help_text += f' Range: {widget.minimum()} to {widget.maximum()}.'
        elif not help_text and isinstance(widget, QLineEdit):
            help_text = widget.placeholderText() or (f'Enter {label}.' if label else '')
        if help_text:
            widget.setToolTip(help_text)
