"""Build page control for Speed separation: a strength from 0 to 100, 0 meaning off.

The row follows the look of Build's option rows (caption and number on one line, the qualifier badge under it, the
plain-words help under that). The number is a plan field, not a check box, so it has its own small enable/refresh rules:
it can be changed only on a full disc image that still has the retail speed code, shows the installed strength
(locked) when the disc already carries it, and stays off on anything else.
"""
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QSpinBox, QVBoxLayout, QWidget

from mod_editor.core import nfl2k5_speed_threshold as patch
from mod_editor.gui.ux_text import WrappedLabel

BADGE = "EXPERIMENTAL / UNWITNESSED"
CAPTION = "Speed separation"


def add_control(layout, refresh):
    """Add the row to ``layout`` and return its spin box (``.badge_label`` and ``.help_label`` ride on it)."""
    row = QWidget()
    column = QVBoxLayout(row)
    column.setContentsMargins(0, 0, 0, 2)
    column.setSpacing(1)
    head = QHBoxLayout()
    head.setSpacing(8)
    head.addWidget(QLabel(patch.BUILD_CAPTION + ":"))
    control = QSpinBox()
    control.setRange(0, 100)
    control.setSpecialValueText("0 (off)")
    control.setAccessibleName(CAPTION + " strength")
    control.setAccessibleDescription(patch.HELP_TEXT)
    control.setToolTip(patch.HELP_TEXT)
    head.addWidget(control)
    head.addStretch(1)
    column.addLayout(head)
    badge = QLabel(BADGE)
    badge.setObjectName("optionBadge")
    badge.setWordWrap(True)
    badge.setContentsMargins(30, 0, 0, 0)
    column.addWidget(badge)
    helper = WrappedLabel(patch.HELP_TEXT)
    helper.setObjectName("throwMuted")
    helper.setWordWrap(True)
    helper.setIndent(30)
    column.addWidget(helper)
    layout.addWidget(row)
    control.badge_label, control.help_label, control.row_widget = badge, helper, row
    control.valueChanged.connect(lambda _value: refresh())
    return control


def refresh(control, state, available=True):
    """Enable, lock or explain the control from ``mod_build.inspect`` output (the Build page's disc state)."""
    state = state or {}
    status = state.get("speed_threshold")
    installed = state.get("speed_threshold_settings") or {}
    is_image = state.get("container") == "xiso"
    value = installed.get("value") if installed.get("status") == "applied" else None
    if status == "applied":
        if type(value) is int:
            control.blockSignals(True)
            control.setValue(value)
            control.blockSignals(False)
        control.setEnabled(False)
        text = ("Already installed on this source" + (f" (strength {value})" if type(value) is int else "")
                + ". To change it, build again from the original disc.")
    elif not available:
        control.setEnabled(False)
        text = "Not available in this release"
    elif status == "foreign":
        control.setEnabled(False)
        text = "Unrecognized source data"
    elif status == "retail" and not is_image:
        control.setEnabled(False)
        text = "Full disc required"
    else:
        control.setEnabled(status == "retail" and is_image)
        text = BADGE
    control.badge_label.setText(text)
    control.badge_label.setVisible(bool(text))


def plan_value(control, state):
    """The strength a build should use: the installed one when locked, 0 when the control is off, else the number."""
    if control.isEnabled():
        return int(control.value())
    state = state or {}
    installed = state.get("speed_threshold_settings") or {}
    if state.get("speed_threshold") == "applied" and installed.get("status") == "applied":
        return int(installed["value"])
    return 0
