"""Offscreen actions on the real tab with contract modules injected via facade."""
from pathlib import Path
import os
import sys
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PyQt5.QtWidgets import QApplication, QComboBox, QPushButton, QSlider, QSpinBox, QDoubleSpinBox
from PyQt5.QtCore import QObject, QThread, pyqtSignal, pyqtSlot
from mod_editor.apf_studio.playcalling_editor_qt import ApfPlayCallingEditor
from tests.mod_editor.test_apf_playcalling_editor_facade import FacadeFixture


class QtTests(FacadeFixture):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        super().setUp()
        self.tasks = []
        def run(label, operation, done, blocking):
            self.tasks.append((label, blocking))
            done(operation(lambda *_: None))
        self.panel = ApfPlayCallingEditor(self.facade, run)
        self.addCleanup(self.panel.close)

    def test_team_first_donors_shared_book_and_distributions(self):
        self.assertEqual(self.panel.team_picker.count(), 24)
        self.assertIn("shared with Team 1", self.panel.book_label.text())
        self.assertGreaterEqual(self.panel.donor_picker.findText("USER-o"), 0)
        self.assertGreaterEqual(self.panel.donor_picker.findText("global-o"), 0)
        self.assertEqual(self.panel.grid.rowCount(), 13)
        self.assertEqual(self.panel.grid.item(0, 1).text(), "8")
        self.assertIn("Ace: 75.0%", self.panel.grid.item(0, 3).text())
        self.assertIn("Flush carries no tight end", self.panel.grid.item(0, 5).text())
        self.assertEqual(self.panel.grid.item(12, 0).text(), "Custom situation")
        self.panel.side_picker.setCurrentIndex(1)
        self.assertEqual(self.panel.grid.rowCount(), 11)
        self.assertEqual(self.panel.grid.item(0, 1).text(), "13")
        self.assertGreaterEqual(self.panel.donor_picker.findText("USER-d"), 0)

    def test_review_own_book_table_then_stage_and_undo(self):
        self.panel.donor_picker.setCurrentIndex(self.panel.donor_picker.findText("USER-o"))
        self.panel.own_team_button.click()
        self.assertEqual(self.panel.plan_table.rowCount(), 1)
        self.assertEqual(self.panel.plan_table.item(0, 2).text(), "USER-o")
        self.assertFalse(self.facade.session.modifications)
        self.panel.confirm_button.click()
        self.assertIn("Team 0 O, used only", self.panel.book_label.text())
        self.panel.undo_button.click()
        self.assertFalse(self.facade.session.modifications)
        self.panel.own_all_button.click()
        self.assertEqual(self.panel.plan_table.rowCount(), 24)
        self.panel.confirm_button.click()
        self.assertEqual(len(self.facade._playcalling.events(self.facade.session)[0]["request"]["assignments"]), 24)

    def test_every_book_lever_stages_and_refreshes(self):
        def kind():
            return self.facade._playcalling.events(self.facade.session)[-1]["request"]["kind"]
        self.panel.ratings[0].setValue(7); self.panel.ratings_button.click()
        self.assertEqual(kind(), "ratings")
        self.assertEqual(self.panel.ratings[0].value(), 7)
        self.panel.play_rating.setValue(0); self.panel.play_rating_button.click()
        self.assertEqual(kind(), "play_rating")
        self.panel.categories_button.click()
        self.assertEqual(self.panel.coverage_table.rowCount(), 11)
        self.panel.confirm_button.click()
        self.assertEqual(kind(), "categories")
        self.panel.tendency.setValue(65); self.panel.tendency_button.click()
        self.assertEqual(kind(), "tendency")
        self.panel.audibles_button.click()
        self.assertEqual(kind(), "audibles")
        self.panel.remove_button.click(); self.panel.confirm_button.click()
        self.assertEqual(kind(), "remove")
        self.assertEqual(self.panel.formation_picker.count(), 1)
        self.panel.retire_picker.setCurrentIndex(self.panel.retire_picker.findData(3))
        self.panel.retire_button.click(); self.panel.confirm_button.click()
        self.assertEqual(kind(), "retire")
        self.assertEqual(self.panel.receipt_table.rowCount(), 7)

    def test_warning_and_refusal_show_coverage_and_retired_names(self):
        self.backend.holes = True
        for callers in ("cpu", "unclassified", "non_cpu"):
            self.backend.lineup_callers = callers
            self.panel.remove_button.click()
            self.assertEqual(self.panel.coverage_table.item(8, 2).text(), "No candidate")
            self.assertIn("Personnel 3", self.panel.review_label.text())
            self.assertEqual(self.panel.confirm_button.isEnabled(), callers == "non_cpu")
        self.panel.confirm_button.click()
        self.assertTrue(self.facade.session.modifications)

    def test_master_off_main_path_all_roles_and_one_click_52(self):
        self.assertFalse(self.panel.master_group.isChecked())
        self.assertEqual(self.panel.master_table.rowCount(), 28)
        self.assertEqual(self.panel.master_table.columnCount(), 14)
        self.assertEqual(self.panel.master_table.item(0, 8).text(), "Tight end")
        self.panel.master_group.setChecked(True)
        self.panel.fix_52_button.click()
        self.assertEqual(self.facade.playcalling_context()["categories"][12].row, 13)
        self.panel.master_row.setValue(2); self.panel.master_row_button.click()
        self.assertEqual(self.facade._playcalling.events(self.facade.session)[-1]["request"]["kind"], "master_row")
        self.panel.roles[0].setCurrentIndex(self.panel.roles[0].findData(9))
        self.panel.roles_button.click()
        self.assertEqual(self.facade._playcalling.events(self.facade.session)[-1]["request"]["kind"], "master_roles")

    def test_experiments_keep_p2_actions_and_every_control_has_explanation(self):
        self.assertEqual(self.panel.experiments.title(), "Experimental patches")
        self.assertEqual(self.panel.curve_side.count(), 2)
        self.assertIn("last-resort fetch", self.panel.legacy.patch_button.text())
        self.assertIn("not a CPU play-calling fix", self.panel.legacy.patch_note.text())
        for cls in (QPushButton, QComboBox, QSlider, QSpinBox, QDoubleSpinBox):
            for control in self.panel.findChildren(cls):
                self.assertTrue(control.accessibleDescription(), control.objectName() or control.accessibleName() or str(control))
        prepared = {"patch_path": "Xenia/patches/curves.patch.toml", "config_path": "Xenia/config.toml"}
        with patch.object(self.facade, "prepare_playcalling_curve", return_value=prepared), \
             patch.object(self.facade, "install_playcalling_curve", return_value={"message": "Installed"}) as install, \
             patch("mod_editor.apf_studio.playcalling_editor_qt.QMessageBox.question", return_value=65536) as consent:
            self.panel.curve_button.click()
            self.assertIn("every book", consent.call_args.args[2])
            install.assert_not_called()

    def test_rating_wording_matches_the_measured_direction(self):
        from mod_editor.apf_studio import playcalling_service as service
        sentences = [service.RATING_EXPLANATION, service.RATING_MAPPING] + [
            slider.accessibleDescription() for slider in self.panel.ratings
        ]
        for sentence in sentences:
            self.assertNotIn("higher rating", sentence.casefold())
            self.assertNotIn("a higher short", sentence.casefold())
        self.assertIn("lower", service.RATING_EXPLANATION.casefold())
        self.assertIn("0/0/0", service.RATING_MAPPING)
        self.assertIn("0.1", service.RATING_MAPPING)
        for slider in self.panel.ratings:
            self.assertIn("lower", slider.accessibleDescription().casefold())
        self.assertIn("0 is called most", self.panel.play_rating.accessibleDescription())
        self.assertEqual(self.panel.master_row.maximum(), 27)

    def test_a_failing_contract_call_shows_a_message_instead_of_crashing(self):
        def broken(*_args, **_kwargs):
            raise TypeError("synthetic contract mismatch")
        with patch.object(self.facade, "playcalling_context", broken):
            self.panel.refresh()
        self.assertIn("synthetic contract mismatch", self.panel.notice.text())
        with patch.object(self.facade, "playcalling_predict", lambda *a, **k: "not a distribution"):
            self.panel.refresh()
        self.assertIn("could not show", self.panel.notice.text())

    def test_stale_worker_result_cannot_replace_new_selection(self):
        queued = []
        self.panel.run_task = lambda *args: queued.append(args)
        self.panel.refresh()
        old = queued.pop(0)
        self.panel.team_picker.setCurrentIndex(1)
        new = queued.pop(0)
        new[2](new[1](lambda *_: None))
        old[2](old[1](lambda *_: None))
        self.assertEqual(self.panel._context["team"]["team_index"], 1)

    def test_worker_replay(self):
        receipt = replay_contract()
        self.assertEqual(receipt["rows"], 13)
        self.assertEqual(receipt["teams"], 24)
        self.assertTrue(receipt["worker_threads"])


def replay_contract():
    """Used by the repository replay tool; all fakes still enter via the facade."""
    app = QApplication.instance() or QApplication([])
    fixture = FacadeFixture()
    fixture.setUp()
    steps, workers = [], []
    class Worker(QThread):
        result = pyqtSignal(object, object)
        def __init__(self, operation, done):
            super().__init__()
            self.operation, self.done = operation, done
        def run(self):
            value = self.operation(lambda *_: None)
            self.result.emit(self, value)
    class Runner(QObject):
        @pyqtSlot(object, object)
        def complete(self, worker, value):
            worker.done(value)
        def submit(self, label, operation, done, blocking):
            worker = Worker(operation, done)
            workers.append(worker)
            worker.result.connect(self.complete)
            worker.start()
    runner = Runner()
    panel = ApfPlayCallingEditor(fixture.facade, runner.submit)
    def pump(label):
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            app.processEvents()
            if not panel._loading and all(w.isFinished() for w in workers):
                steps.append(label)
                return
            time.sleep(.002)
        raise AssertionError("Worker replay timed out: " + label)
    try:
        pump("team books and situation grid loaded in worker")
        assert panel.grid.rowCount() == 13, panel.notice.text()
        panel.ratings[0].setValue(7); panel.ratings_button.click()
        pump("formation rating staged and calls recomputed")
        assert panel.ratings[0].value() == 7, panel.notice.text()
        panel.own_team_button.click(); pump("own-book table reviewed")
        panel.confirm_button.click(); pump("independent team book staged")
        assert "Team 0 O" in panel.book_label.text(), panel.notice.text()
        path = fixture.root / "replay.apf2k8mod"
        fixture.facade.session.save_project(path)
        fixture.facade.session.load_project(path)
        panel.set_context(); pump("project reopened and preview replayed")
        panel.undo_button.click(); pump("session undo and preview recomputed")
        return {"steps": steps, "rows": panel.grid.rowCount(), "teams": panel.team_picker.count(),
                "worker_threads": len(workers), "evidence": "PROVED synthetic contract replay; P3 integration and gameplay UNWITNESSED"}
    finally:
        for worker in workers:
            worker.wait(15000)
        panel.close()
        fixture.doCleanups()


if __name__ == "__main__":
    unittest.main()
