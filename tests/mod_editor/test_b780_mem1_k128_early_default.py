"""b780-mem1: the K128 early form comes with 128 MB memory when a user ticks it, and Check my project names the late form.

With the late form the pregame intro's camera script no longer fits at retail-model stadiums at 128 MB on this
release's content (EMU1 H1R2 and H1V8B: heap B 6,400 and 66,304 B against 73,856 B; the flyover loops). The early
form makes the room (EMU1 T2a: heap B 214,400 B, kickoff). A user's tick on 128 MB memory now ticks Bigger graphics
memory too (untick it to opt out); a project load keeps the saved choice; Check my project notes the late form.
"""
import os
from pathlib import Path
import sys
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from PyQt5.QtWidgets import QApplication  # noqa: E402
from mod_editor.core import mod_build  # noqa: E402
from mod_editor.core import nfl2k5_project_check as project_check  # noqa: E402
from mod_editor.gui import beta62_options as r62_ui  # noqa: E402
from mod_editor.gui.build_panel_qt import BuildPanel  # noqa: E402


class CheckMyProjectTests(unittest.TestCase):
    def notes(self, **options):
        plan = mod_build.BuildPlan('source.iso', 'output.iso')
        for key, value in options.items():
            setattr(plan, key, value)
        return [f for f in project_check.check(plan, run_preflight=False).findings if f.code == 'k128.early_off']

    def test_the_late_form_gets_a_note_and_the_early_form_or_no_k128_does_not(self):
        found = self.notes(k128_memory=True, k128_roster_heap=True)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].severity, project_check.NOTE)
        self.assertIn('Bigger graphics memory', found[0].fix)
        self.assertIn('Baltimore', found[0].detail)
        self.assertEqual(self.notes(k128_memory=True, k128_roster_heap=True, k128_early=True), [])
        self.assertEqual(self.notes(), [])

    def test_no_em_dashes_in_the_note(self):
        found = self.notes(k128_memory=True)[0]
        for text in (found.title, found.detail, found.fix):
            self.assertNotIn('—', text)


class BuildPanelDefaultTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.panel = BuildPanel()
        self.panel.apply_state(dict(path='source.iso', container='xiso',
                                    **{k: 'retail' for k in self.panel._boxes()}))
        boxes = self.panel._boxes()
        self.k128, self.early, self.heap = boxes['k128_memory'], boxes['k128_early'], boxes['k128_roster_heap']

    def tearDown(self):
        self.panel.deleteLater()
        self.app.processEvents()

    def test_the_mapping_names_only_the_early_form(self):
        self.assertEqual(r62_ui.DEFAULT_ON_CHILDREN, {'k128_memory': ('k128_early',)})
        self.assertIn('k128_early', r62_ui.CHILDREN['k128_memory'])

    def test_a_users_tick_brings_the_early_form_and_the_user_can_untick_it(self):
        self.assertFalse(self.early.isChecked())
        self.k128.click()
        self.assertTrue(self.k128.isChecked())
        self.assertTrue(self.early.isChecked())
        self.assertFalse(self.heap.isChecked())               # only the early form comes along
        plan = self.panel.plan()
        self.assertTrue(plan.k128_memory and plan.k128_early)
        self.early.click()
        self.assertTrue(self.k128.isChecked())
        self.assertFalse(self.early.isChecked())
        self.assertFalse(self.panel.plan().k128_early)
        self.k128.click()                                     # off takes the children with it, as before
        self.assertFalse(self.early.isChecked())

    def test_a_project_load_keeps_the_saved_choice(self):
        self.k128.setChecked(True)                            # programmatic, as apply_state and presets do
        self.assertFalse(self.early.isChecked())


if __name__ == '__main__':
    unittest.main()
