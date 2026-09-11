"""Shared, synchronous Build/Gameplay playbook selection gate.

Qt widgets are duck typed so the rule has no GUI import or application startup.
Source eligibility is recomputed, never restored from a stale enabled flag.
"""
from dataclasses import replace

from mod_editor.core.mod_build import BuildPlan, PLAYBOOK_OPTION_LABELS, validate_plan


def refresh_playbook_controls(checks, helpers, state, available=None):
    state = state or {}
    available = available or {}
    selected = {
        key: (key in checks and checks[key].isChecked()) or state.get(key) == "applied"
        for key in PLAYBOOK_OPTION_LABELS
    }
    plan = BuildPlan("", "", **selected)
    blockers = validate_plan(plan)
    for key in PLAYBOOK_OPTION_LABELS:
        if key not in checks:
            continue
        check = checks[key]
        helper = helpers[key]
        if helper.property("playbook_original_help") is None:
            helper.setProperty("playbook_original_help", helper.text())
        # A selected option remains available to untick, including an invalid
        # restored project. Unticked options cannot introduce a conflict.
        reasons = validate_plan(replace(plan, **{key: True}))
        if key != "playbook_pair":
            reasons = [reason for reason in reasons if PLAYBOOK_OPTION_LABELS[key] in reason]
        reason = " ".join(reasons)
        eligible = (state.get("container") == "xiso" and state.get(key) == "retail"
                    and available.get(key, True))
        check.setEnabled(eligible and (check.isChecked() or not reason))
        helper.setText(reason or helper.property("playbook_original_help"))
        helper.setVisible(bool(helper.text()))
        if reason:
            check.setToolTip(reason)
        elif eligible:
            check.setToolTip("")
    return blockers
