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
            box.setChecked(value == "matte" if key == "helmet_finish"
                           else value == "jukebox_menus" if key == "music_policy"
                           else value != "retail" if key == "cpu_money_downs" else bool(value))
        panel.colour_lighting.set_settings(choices["modern_color_settings"])
        panel.colour_lighting.set_active(choices["modern_color"])
        panel.ceiling_spin.setValue(round(choices["max_deep_yards"]))
        panel.arc_spin.setValue(round(choices["arc"] * 100))
        if hasattr(panel, "speed_threshold_spin"):  # b780-cv5: the Build page's Speed separation strength
            panel.speed_threshold_spin.setValue(choices["speed_threshold"])
        panel._momentum_last_positive = choices["momentum"] or 50
        panel._collision_last_positive = choices["momentum_collision_level"] or 50
        for field, value in (("scorebug_watermark_combo", choices["scorebug_watermark"]),
                             ("momentum_level", choices["momentum"]),
                             ("momentum_collision_level", choices["momentum_collision_level"]),
                             ("cpu_money_downs_level", choices["cpu_money_downs"] or "retail"),
                             ("accelerated_clock_minimum", choices["accelerated_clock_minimum_seconds"]),
                             ("decided_clock_margin", choices["decided_clock_margin"]),
                             ("decided_clock_seconds", choices["decided_clock_seconds"]),
                             ("cpu_scrambles_level", choices["cpu_scrambles"]),
                             ("abilities_week", choices["abilities_off_week"]),
                             ("uniform_choice_mode", choices["uniform_choice"] or "choice"),
                             ("helmet_finish_combo", choices["helmet_finish"] or "glossy"),
                             ("hires_scale_combo", choices["hires_scale"]),
                             ("hires_target_combo", choices["hires_target"])):
            _combo(getattr(panel, field), value)
        panel.screen_timing_combo.setCurrentText(choices["screen_timing"] or "D")
        for key, box in getattr(panel, "abilities_lock_checks", {}).items():
            box.setChecked(bool(choices.get(key, True)))
        for key in ("team_history", "career_stats", "prospect_names", "roster_edits", "espn25_plan", "weather_plan", "music_project",
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
        self._dropped: list[str] = []      # keys whose copy was dropped while another copy was in flight (see _copy)
        self._copying = None               # (source, destination, value) of the copy in flight
        self.shared = set(build._boxes()) & set(gameplay.checks)
        self._key_of = {}
        for key in self.shared:
            self._key_of[id(build._boxes()[key])] = key
            self._key_of[id(gameplay.checks[key])] = key
        for key in self.shared:
            build._boxes()[key].toggled.connect(lambda _on, k=key: self.copy_from_build(k))
            gameplay.checks[key].toggled.connect(lambda _on, k=key: self.copy_from_gameplay(k))
        for name in ("momentum_level", "momentum_collision_level", "cpu_money_downs_level", "accelerated_clock_minimum", "decided_clock_margin", "decided_clock_seconds", "cpu_scrambles_level", "screen_timing_combo", "helmet_finish_combo"):
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
        for name in ("momentum_level", "momentum_collision_level", "cpu_money_downs_level", "accelerated_clock_minimum", "decided_clock_margin", "decided_clock_seconds", "cpu_scrambles_level", "screen_timing_combo", "helmet_finish_combo"):
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
            if self.busy and self._copying is not None and not (
                    (source, destination) == (self._copying[1], self._copying[0]) and source.isChecked() == self._copying[2]):
                # Not the echo of the copy in flight (every effective copy toggles its destination, which asks for the copy
                # back with the value just copied): a rule on the destination page ticked or cleared another box, or put
                # this one back, while the copy ran.
                key = self._key_of.get(id(source))
                if key is not None and key not in self._dropped:
                    self._dropped.append(key)
            return
        self.busy = True
        self._copying = (source, destination, source.isChecked())
        self._dropped = []
        try:
            destination.setChecked(source.isChecked())
        finally:
            self.busy = False
            self._copying = None
        # While `busy` was set, the destination page's own rules (a child that needs its parents, a rival that must go
        # off) could tick or clear other boxes, and those toggles were dropped. Ticking ESPN scorebug effects on Game
        # Fixes left Build with the scorebug and extra patch space ticked while Game Fixes showed both unticked. The
        # Build page owns the plan, so mirror just those boxes from Build onto Game Fixes: the two pages never disagree.
        # Only those boxes, and not a full refresh: this copy may be the first of several slots of one click (Game Fixes'
        # own rule ticks a parent before the link copies the child), and a full refresh wiped the box the user had just
        # ticked because its own copy had not been made yet (b780 studio1: Stop man-coverage spins on Game Fixes).
        if self._dropped:
            dropped, self._dropped = self._dropped, []
            self.settle(dropped)
        self.changed()

    def settle(self, keys):
        """Make Game Fixes show what Build holds for these boxes (Build owns the plan)."""
        with quiet(self.gameplay):
            for key in keys:
                self.gameplay.checks[key].setChecked(self.build._boxes()[key].isChecked())
            self.gameplay._refresh()


def observe_build_choices(panel, changed):
    """Persist controls which are not shared with the Gameplay page too."""
    colour_lighting = getattr(panel, "colour_lighting", None)
    if colour_lighting is not None:
        colour_lighting.changed.connect(changed)
    for widget in panel.findChildren(QObject):
        if isinstance(widget, QCheckBox):
            widget.toggled.connect(changed)
        elif isinstance(widget, QComboBox) and widget is not getattr(panel, "equipment_refit_choice", None):
            # This picker targets a refit action; refreshing its rows is not a Build edit.
            widget.currentIndexChanged.connect(changed)
        elif isinstance(widget, (QSpinBox, QDoubleSpinBox)):
            widget.valueChanged.connect(changed)
        elif isinstance(widget, QLineEdit) and widget not in (panel.source_field, panel.target_field):
            widget.textChanged.connect(changed)
        elif isinstance(widget, QPlainTextEdit) and not widget.isReadOnly():
            # Build summaries are refreshed by the shell, not authored project choices.
            widget.textChanged.connect(changed)
