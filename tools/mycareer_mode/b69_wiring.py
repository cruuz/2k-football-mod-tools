"""Produce a reviewable protected-file patch. Never writes protected files."""
from pathlib import Path
import difflib

ROOT = Path(__file__).resolve().parents[2]


def panel_source():
    path = ROOT / 'mod_editor/gui/my_career_panel_qt.py'
    original = path.read_text()
    updated = original
    def replace(before, after):
        nonlocal updated
        if updated.count(before) != 1:
            raise ValueError(f'MyCareer panel insertion differs: {before[:60]}')
        updated = updated.replace(before, after)
    replace('from mod_editor.core import nfl2k5_my_career as career',
            'from mod_editor.core import nfl2k5_my_career as career\n'
            'from mod_editor.core import nfl2k5_my_career_prospects as prospects')
    replace('        description = QLabel(career.HELP_TEXT)', '''        description = QLabel(
            "Create MyPlayer in the game, or prepare a signed draft save here. "
            "Choose who calls the plays in Apartment Settings. Fast forward handles "
            "MyPlayer's time off the field. Experimental: this build still needs a played check.")''')
    replace('        form.addRow("Ratings", self.template)', '''        form.addRow("Prototype", self.template)
        self.prospect = QComboBox()
        for tier, (label, overall, goal) in enumerate(prospects.TIERS):
            self.prospect.addItem(label if overall is None else f"{label} ({overall} OVR)", tier)
        form.addRow("Prospect tier", self.prospect)
        prospect_help = QLabel(
            "1st Day: backup, Slot WR or Nickel CB. 2nd Day: third string or fourth WR/CB. "
            "3rd Day: third string or fifth WR/CB. Undrafted: bottom of the depth chart. "
            "The career keeps the tier's goal label. Senior Bowl play, Combine drills and Pro Day are planned. "
            "Gunslinger QB uses the existing Pocket QB ratings.")
        prospect_help.setWordWrap(True)
        form.addRow(prospect_help)''')
    replace('        form.addRow(self.starter)', '''        form.addRow(self.starter)
        self.prospect.currentIndexChanged.connect(
            lambda: self.starter.setEnabled(self.prospect.currentData() == 0))''')
    replace('        settings_form.addRow("Supersim", self.career_supersim)', '''        settings_form.addRow("Supersim", self.career_supersim)
        self.career_playcall = QComboBox()
        self.career_playcall.addItems(career_save.PLAYCALL_CHOICES)
        self.career_playcall.setEnabled(False)
        settings_form.addRow("Who calls the plays", self.career_playcall)
        caller_help = QLabel(
            "You call every play is the default. By position lets a QB call offense and an ILB "
            "(LB in the one-pool roster) call defense. Coach calls the plays lets you execute "
            "the coach's choice. You keep control before the snap and during the play. "
            "Change the same saved choice in Apartment > Settings.")
        caller_help.setWordWrap(True)
        settings_form.addRow(caller_help)''')
    replace('        for template in career.templates_for(code, scheme=self._position_scheme):\n'
            '            self.template.addItem(template.label, template.variant)',
            '        for label, variant in prospects.prototypes(code, scheme=self._position_scheme):\n'
            '            self.template.addItem(label, variant)\n'
            '        if code == 0:\n'
            '            self.template.setCurrentIndex(3)  # historical Pocket default')
    replace('            return career_save.supersim_choice(container.savegame)',
            '            return (career_save.supersim_choice(container.savegame),\n'
            '                    career_save.playcall_choice(container.savegame))')
    replace('        def loaded(choice):', '        def loaded(choices):\n            choice, caller = choices')
    replace('            self.career_supersim.setCurrentText(choice)',
            '            self.career_supersim.setCurrentText(choice)\n'
            '            self.career_playcall.setCurrentText(caller)\n'
            '            self.career_playcall.setEnabled(True)')
    replace('            self.result.setText(f"Saved Supersim setting: {choice}.")',
            '            self.result.setText(f"Saved settings: {choice}. {caller}.")')
    replace('        choice = self.career_supersim.currentText()',
            '        choice = self.career_supersim.currentText()\n'
            '        caller = self.career_playcall.currentText()')
    replace('                "The save signature and read-back passed.")',
            '                f"{receipt[\'playcall\']}. The save signature and read-back passed.")')
    replace('        self._run(lambda: career_save.write_supersim(source, target, choice), exported)',
            '        self._run(lambda: career_save.write_settings(\n'
            '            source, target, supersim=choice, playcall=caller), exported)')
    replace('        self.career_supersim.setEnabled(False)\n        self.create_button.setEnabled(False)',
            '        self.career_supersim.setEnabled(False)\n'
            '        self.career_playcall.setEnabled(False)\n        self.create_button.setEnabled(False)')
    replace('            self.career_supersim.setEnabled(bool(self._career_settings_source))',
            '            self.career_supersim.setEnabled(bool(self._career_settings_source))\n'
            '            self.career_playcall.setEnabled(bool(self._career_settings_source))')
    replace('                       starter_lock=self.starter.isChecked(), scheme=self._position_scheme)',
            '                       starter_lock=self.starter.isChecked(), scheme=self._position_scheme,\n'
            '                       prospect_tier=self.prospect.currentData())')
    return original, updated


def build_source():
    path = ROOT / 'mod_editor/core/mod_build.py'
    original = path.read_text()
    before = '        plan = replace(plan, draft_ai=True)  # generic MyCareer (M3 draft) reuses the draft-AI implementation'
    after = before.replace('draft_ai=True)', 'draft_ai=True, depth_locks=True)') + '''
    if plan.my_career and plan.my_career_setup:
        # Tiered prepared careers carry initial rank/side locks. Keep those
        # locks through native depth sorting; ordinary creation is unchanged.
        import struct
        if struct.unpack_from("<I", r62["my_career_setup"], 212)[0]:
            plan = replace(plan, depth_locks=True)'''
    if original.count(before) != 1:
        raise ValueError('MyCareer Build dependency insertion differs')
    return original, original.replace(before, after)


def patch():
    return ''.join(''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                         fromfile='a/' + path, tofile='b/' + path))
        for path, (before, after) in (
            ('mod_editor/gui/my_career_panel_qt.py', panel_source()),
            ('mod_editor/core/mod_build.py', build_source())))


if __name__ == '__main__':
    print(patch(), end='')
