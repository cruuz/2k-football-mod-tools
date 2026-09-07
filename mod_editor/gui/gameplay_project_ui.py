"""One set of Gameplay/Build choices, saved with the project.

Protected panel call sites are supplied in the Discord bugs WIRING section.
No writer runs here. Synchronization only changes the effective BuildPlan.
"""
from contextlib import contextmanager
from copy import deepcopy

from PyQt5.QtCore import QObject, QSignalBlocker
from PyQt5.QtWidgets import QCheckBox, QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox, QPlainTextEdit
from mod_editor.core import nfl2k5_build_settings as saved


@contextmanager
def quiet(panel):
    blockers = [QSignalBlocker(widget) for widget in panel.findChildren(QObject)]
    try:
        yield
    finally:
        for blocker in blockers:
            blocker.unblock()


def capture(panel):
    state = saved.from_plan(panel.plan())
    state.update(panel.music_build_settings())
    state.update(deepcopy(panel._senior_bowl_options))
    # A prepared file can exist before its option is enabled.
    state["my_career_setup"] = panel.my_career_setup_field.text().strip() or None
    return saved.build_settings(state)


def _combo(widget, value):
    index = widget.findData(value)
    if index < 0:
        index = widget.findText(str(value))
    if index < 0:
        widget.addItem(str(value), value)
        index = widget.count() - 1
    widget.setCurrentIndex(index)


def restore(panel, state):
    choices = {**saved.from_plan(saved.to_plan({}, "", "")), **saved.build_settings(state)}
    with quiet(panel):
        for key, box in panel._boxes().items():
            value = choices[key]
            box.setChecked(value == "jukebox_menus" if key == "music_policy" else bool(value))
        panel.ceiling_spin.setValue(round(choices["max_deep_yards"]))
        panel.arc_spin.setValue(round(choices["arc"] * 100))
        panel._momentum_last_positive = choices["momentum"] or 50
        panel._collision_last_positive = choices["momentum_collision_level"] or 50
        for field, value in (("momentum_level", choices["momentum"]),
                             ("momentum_collision_level", choices["momentum_collision_level"]),
                             ("abilities_week", choices["abilities_off_week"]),
                             ("uniform_choice_mode", choices["uniform_choice"] or "choice"),
                             ("hires_scale_combo", choices["hires_scale"]),
                             ("hires_target_combo", choices["hires_target"])):
            _combo(getattr(panel, field), value)
        panel.screen_timing_combo.setCurrentText(choices["screen_timing"] or "D")
        for key in ("team_history", "career_stats", "prospect_names", "roster_edits", "music_project",
                    "music_library", "hires_folder", "scorebug_folder", "my_career_setup", "name", "author"):
            getattr(panel, key + "_field").setText(choices[key] or "")
        panel.notes_field.setPlainText(choices["notes"])
        panel.set_star_players(choices["player_tags"])
        panel.set_playbook_packs(choices["playbook_packs"])
        panel.set_commentary(saved.to_plan(choices, "", "").commentary)
        panel._music_shuffle_selection = deepcopy(choices["music_shuffle_selection"])
        panel._guardian_players = deepcopy(choices["guardian_players"])
        panel.guardian_everyone_practice_check.setChecked(choices["guardian_everyone_practice"])
        panel.set_senior_bowl_options({key: choices[key] for key in ("senior_bowl", "senior_bowl_settings", "senior_bowl_seed")})
        for family, box in panel._hires_family_checks.items():
            box.setChecked(family in choices["hires_families"])
        panel._refresh()


class GameplayBuildLink:
    """Last user edit wins in either view; repeated checks never enqueue work."""
    def __init__(self, build, gameplay, changed, suspended=lambda: False):
        self.build, self.gameplay, self.changed = build, gameplay, changed
        self.suspended = suspended
        self.busy = False
        self.shared = set(build._boxes()) & set(gameplay.checks)
        for key in self.shared:
            build._boxes()[key].toggled.connect(lambda _on, k=key: self.copy_from_build(k))
            gameplay.checks[key].toggled.connect(lambda _on, k=key: self.copy_from_gameplay(k))
        for name in ("momentum_level", "momentum_collision_level", "screen_timing_combo"):
            for origin in (build, gameplay):
                getattr(origin, name).currentIndexChanged.connect(
                    lambda _index, p=origin: self.copy_levels(p))
        for origin in (build, gameplay):
            origin.guardian_everyone_practice_check.toggled.connect(lambda _on, p=origin: self.copy_levels(p))
            origin.my_career_setup_field.textChanged.connect(lambda _text, p=origin: self.copy_levels(p))
        self.refresh_from_build()

    def refresh_from_build(self):
        with quiet(self.gameplay):
            for key in self.shared:
                self.gameplay.checks[key].setChecked(self.build._boxes()[key].isChecked())
            self._levels(self.build, self.gameplay)
            self.gameplay._refresh()

    def _levels(self, origin, destination):
        for name in ("momentum_level", "momentum_collision_level", "screen_timing_combo"):
            source = getattr(origin, name)
            _combo(getattr(destination, name), source.currentData() if name != "screen_timing_combo" else source.currentText())
        destination._momentum_last_positive = origin._momentum_last_positive
        destination._collision_last_positive = origin._collision_last_positive
        destination.guardian_everyone_practice_check.setChecked(origin.guardian_everyone_practice_check.isChecked())
        destination.my_career_setup_field.setText(origin.my_career_setup_field.text())

    def copy_levels(self, origin):
        if self.busy or self.suspended():
            return
        self.busy = True
        try:
            destination = self.gameplay if origin is self.build else self.build
            with quiet(destination):
                self._levels(origin, destination)
                destination._refresh()
        finally:
            self.busy = False
        self.changed()

    def copy_from_build(self, key):
        self._copy(self.build._boxes()[key], self.gameplay.checks[key])

    def copy_from_gameplay(self, key):
        self._copy(self.gameplay.checks[key], self.build._boxes()[key])

    def _copy(self, source, destination):
        if self.busy or self.suspended():
            return
        self.busy = True
        try:
            destination.setChecked(source.isChecked())
        finally:
            self.busy = False
        self.changed()


def observe_build_choices(panel, changed):
    """Persist controls which are not shared with the Gameplay page too."""
    for widget in panel.findChildren(QObject):
        if isinstance(widget, QCheckBox):
            widget.toggled.connect(changed)
        elif isinstance(widget, QComboBox):
            widget.currentIndexChanged.connect(changed)
        elif isinstance(widget, (QSpinBox, QDoubleSpinBox)):
            widget.valueChanged.connect(changed)
        elif isinstance(widget, QLineEdit) and widget not in (panel.source_field, panel.target_field):
            widget.textChanged.connect(changed)
        elif isinstance(widget, QPlainTextEdit):
            widget.textChanged.connect(changed)
