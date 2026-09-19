"""Standalone offscreen widget and worker wiring checks; no display or disc."""
import importlib.util
import os
from pathlib import Path
import sys
import time
import unittest
from unittest import mock

os.environ["QT_QPA_PLATFORM"] = "offscreen"
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
HAVE_QT = importlib.util.find_spec("PyQt5") is not None


@unittest.skipUnless(HAVE_QT, "offscreen MyCareer page tests require PyQt5")
class PanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PyQt5.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from mod_editor.gui import my_career_panel_qt as panel
        self.module = panel
        self.page = panel.MyCareerPanel()
        self.addCleanup(self.page.close)

    def finish(self):
        deadline = time.monotonic() + 5
        while self.page._task is not None and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.005)
        self.assertIsNone(self.page._task, "worker did not finish within 5 seconds")

    def test_no_implicit_write_and_missing_input_is_explained(self):
        with mock.patch.object(self.module.crib, "plan") as plan:
            self.page.set_source("source.iso")
            self.assertFalse(self.page.rebuild_button.isEnabled())
            self.assertIsNone(self.page._task)
            plan.assert_not_called()
        self.page._create()
        self.assertIn("first and last name", self.page.result.text())

    def test_setup_signal_and_worker_error_restore_controls(self):
        self.page.save.setText("source.zip")
        self.page.output.setText("new-folder")
        self.page.first.setText("My")
        self.page.last.setText("Player")
        delivered = []
        self.page.setup_ready.connect(delivered.append)
        with mock.patch.object(self.module.career, "prepare_save", return_value={"output": "new-folder", "myplayer": "My Player"}):
            self.page._create()
            self.finish()
        self.assertEqual(delivered, [str(Path("new-folder/MyCareer.json"))])
        self.assertIn("normal draft", self.page.result.text())
        with mock.patch.object(self.module.career, "prepare_save", side_effect=ValueError("draft stage required")):
            self.page._create()
            self.finish()
        self.assertEqual(self.page.result.text(), "draft stage required")
        self.assertTrue(self.page.create_button.isEnabled())

    def test_position_choice_drives_templates_contract_and_options(self):
        from mod_editor.core import nfl2k5_my_career as career
        self.assertEqual(self.page.position.count(), 11)
        self.assertEqual(self.page.position.currentData(), 0)
        self.assertEqual([self.page.template.itemText(i) for i in range(self.page.template.count())],
                         ["Scrambling QB", "Gunslinger QB", "Balanced QB", "Pocket QB"])
        self.assertTrue(self.page.contract.text().startswith("QB: proved"))
        self.page.position.setCurrentIndex(self.page.position.findData(16))
        self.assertEqual(self.page.position.currentText(), "EDGE (Edge Rusher)")
        self.assertEqual(self.page.template.count(), 3)
        self.assertEqual([self.page.template.itemText(i) for i in range(3)],
                         ["Run Stop DL", "Pass Rush DL", "Balanced DL"])
        self.assertTrue(self.page.contract.text().startswith("DL: proved"))
        self.page.position.setCurrentIndex(self.page.position.findData(3))
        self.assertEqual([self.page.template.itemText(i) for i in range(3)], ["Speed WR", "Hands WR", "Balanced WR"])
        self.page.template.setCurrentIndex(1)
        self.assertTrue(self.page.starter.isChecked())
        self.page.starter.setChecked(False)
        self.page.save.setText("source.zip")
        self.page.output.setText("new-folder")
        self.page.first.setText("My")
        self.page.last.setText("Player")
        self.page.camera.setCurrentIndex(1)
        self.page.port.setValue(3)
        with mock.patch.object(self.module.career, "prepare_save",
                               return_value={"output": "new-folder", "myplayer": "My Player", "position": "WR"}) as prepare:
            self.page._create()
            self.finish()
        self.assertEqual(prepare.call_args.args, ("source.zip", "new-folder"))
        self.assertEqual(prepare.call_args.kwargs, dict(first="My", last="Player", position=3, template=1,
                                                        port=2, camera=1, starter_lock=False, scheme="retail", prospect_tier=0, college=None, jersey=None, height=None, weight=None))
        self.assertIn("(WR)", self.page.result.text())
        self.assertIn("Game Modes", self.page.result.text())

    def test_roster_modes_identity_colleges_and_events_signal(self):
        from mod_editor.core import nfl2k5_my_career_events as events
        from tests.mod_editor.test_nfl2k5_my_career_events import player
        self.page.position.setCurrentIndex(self.page.position.findData(10))
        self.page.set_position_pools(True)
        self.assertEqual(self.page.position.count(), 10)
        self.assertEqual(self.page.position.currentData(), 11)
        self.assertEqual(self.page.position.findData(10), -1)
        self.assertTrue(self.page.position.currentText().startswith('LB '))
        self.assertEqual(self.page.template.count(), 3)
        self.page.set_position_pools(False)
        self.assertEqual(self.page.position.count(), 11)
        self.assertGreaterEqual(self.page.position.findData(10), 0)
        self.page.save.setText('source.zip')
        self.page.output.setText('new-folder')
        self.page.first.setText('My')
        self.page.last.setText('Player')
        self.page.jersey.setValue(8)
        self.page.height.setValue(80)
        self.page.weight.setValue(350)
        self.page.college.addItem('Michigan', 'Michigan')
        self.page.college.setCurrentIndex(1)
        ledger = events.new_ledger(player())
        received = []
        self.page.earned_events_ready.connect(received.append)
        with mock.patch.object(self.module.career, 'prepare_save', return_value={
                'output': 'new-folder', 'myplayer': 'My Player', 'earned_events': ledger}) as prepare:
            self.page._create()
            self.finish()
        for key, value in dict(jersey=8, height=80, weight=350, college='Michigan').items():
            self.assertEqual(prepare.call_args.kwargs[key], value)
        self.assertEqual(received, [ledger])
        self.assertEqual(self.page.advisory_setup.text(), str(Path('new-folder')/'MyCareer.json'))
        self.page.save.setText('other.zip')
        self.assertEqual(self.page.college.count(), 1)
        self.assertIsNone(self.page.college.currentData())

    def test_advisory_is_read_only_refreshable_and_invalidated(self):
        report = {'label': 'Draft Advisory estimate', 'note': 'Does not change the draft.',
                  'clubs': [dict(club='Example', position_count=1, target=2, maximum=4,
                                 shortfall=1, cut_risk='Low', projected_position_rank=2, projected_roster=53)]}
        self.page.advisory_setup.setText('prepared/MyCareer.json')
        with mock.patch.object(self.module.advisory, 'review_prepared', return_value=report) as review:
            self.page._review_advisory()
            self.finish()
        review.assert_called_once_with('prepared/MyCareer.json', scheme='retail')
        self.assertIn('53-man cut risk: Low', self.page.advisory_result.text())
        self.page.set_position_pools(True)
        self.assertNotIn('Example', self.page.advisory_result.text())
        with mock.patch.object(self.module.advisory, 'review_prepared', side_effect=ValueError('class changed')):
            self.page._review_advisory()
            self.finish()
        self.assertEqual(self.page.result.text(), 'class changed')
        self.assertNotIn('Example', self.page.advisory_result.text())
        self.assertTrue(self.page.advisory_button.isEnabled())

    def test_review_is_invalidated_when_image_changes(self):
        self.page.set_source("one.iso")
        with mock.patch.object(self.module.crib, "plan", return_value={"disc_bytes_reclaimed": 1024}):
            self.page._review()
            self.finish()
        self.assertTrue(self.page.rebuild_button.isEnabled())
        self.assertIn("Trophy Room", self.page.result.text())
        self.page.set_source("two.iso")
        self.assertIsNone(self.page._plan)
        self.assertFalse(self.page.rebuild_button.isEnabled())


if __name__ == "__main__":
    unittest.main()
