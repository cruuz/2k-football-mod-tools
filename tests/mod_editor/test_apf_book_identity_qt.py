"""Offscreen action/review contracts, with synthetic identity and mocked disk work."""
from pathlib import Path
import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from PyQt5.QtWidgets import QApplication
from mod_editor.apf_studio.book_identity_qt import BookIdentityPanel
from mod_editor.core import apf2k8_book_identity as identity
from mod_editor.core.errors import ValidationError


class PanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        def runner(_title, operation, callback, _busy):
            callback(operation(lambda *_args: None))
            return True
        self.panel = BookIdentityPanel(runner)
        self.parsed = identity.RosterIdentity(
            (identity.Label(0, 100, "Used", "O-ZoneBlock", "offense"),
             identity.Label(1, 112, "Independent", "O-ZoneBlock", "offense"),
             identity.Label(2, 124, "Defense", "X-43Cover2", "defense")),
            (identity.Team(0, "Synthetic Team", 0, 2, 200, 204),), "synthetic")
        self.report = identity.book_identity_report(self.parsed)

    def tearDown(self):
        self.panel.close()

    def load(self):
        with patch.object(identity, "read_disc_roster", return_value=b"synthetic"), \
             patch.object(identity, "parse_roster_identity", return_value=self.parsed), \
             patch.object(identity, "disc_book_identity_report", return_value=self.report):
            self.panel.load_path(Path("synthetic-game/0A"))

    def test_identity_and_unused_label_picker_require_a_source(self):
        self.assertFalse(self.panel.review.isEnabled())
        self.assertFalse(self.panel.build.isEnabled())
        self.load()
        self.assertEqual(self.panel.table.rowCount(), 2)
        self.assertEqual(self.panel.label.count(), 1)
        self.assertEqual(self.panel.label.currentData(), 1)
        self.assertTrue(self.panel.review.isEnabled())
        with self.assertRaises(ValidationError):
            self.panel.build_to(Path("should-never-be-created"))

    def test_review_is_invalidated_by_selection_change(self):
        self.load()
        class Plan:
            report = {"book_identity": self.report, "status": "UNWITNESSED"}
        with patch("mod_editor.apf_studio.book_identity_qt.clone.compile_unlock", return_value=Plan()) as compile_mock:
            self.panel.review_selection()
        request = compile_mock.call_args.args[1][0]
        self.assertEqual((request.label_id, request.team_index), (1, 0))
        self.assertTrue(self.panel.build.isEnabled())
        self.panel.action.setCurrentIndex(1)
        self.assertFalse(self.panel.build.isEnabled())
        self.assertIsNone(self.panel.reviewed)
        self.assertTrue(self.panel.team.isEnabled())

    def test_preset_fills_donor_and_keeps_team_label_and_donor_editable(self):
        self.load()
        self.panel.action.setCurrentIndex(1)
        self.assertEqual(self.panel.donor.currentData(), "O-ZoneBlock")
        self.assertTrue(all(w.isEnabled() for w in (self.panel.team, self.panel.label, self.panel.donor)))
        self.assertIn("play membership and audible slots", self.panel.recipe_note.text())
        self.panel.donor.setCurrentIndex(self.panel.donor.findData("O-ManBlock"))
        self.assertEqual(self.panel.action.currentData(), "clone")
        self.assertEqual(self.panel.donor.currentData(), "O-ManBlock")

    def test_preset_build_clones_selected_team_and_opens_that_output_for_editing(self):
        self.load()
        self.panel.action.setCurrentIndex(1)
        class Plan:
            report = {"book_identity": self.report,
                      "roster_binding": {"changes": [{"after_type": "Independent"}]}}
        plan = Plan()
        with patch("mod_editor.apf_studio.book_identity_qt.clone.compile_unlock", return_value=plan) as compile_mock:
            self.panel.review_selection()
        self.assertEqual(compile_mock.call_args.kwargs["preset_ids"], ("wide-zone",))
        request = compile_mock.call_args.args[1][0]
        self.assertEqual((request.team_index, request.label_id, request.donor_type), (0, 1, "O-ZoneBlock"))
        with patch("mod_editor.apf_studio.book_identity_qt.clone.build_new_folder",
                   return_value={"runtime_status": "UNWITNESSED"}) as build_mock:
            self.panel.build_to(Path("synthetic-output"))
        self.assertIs(build_mock.call_args.args[0], plan)
        self.assertEqual(self.panel._edit_index, Path("synthetic-output/0A"))
        self.assertEqual(self.panel._edit_name, "Independent")
        self.assertTrue(self.panel.edit.isEnabled())
        self.assertIn("UNWITNESSED", self.panel.status.text())
        self.assertFalse(self.panel.build.isEnabled())

    def test_busy_does_not_allow_another_clone_review_or_build(self):
        self.load()
        self.panel.set_busy(True)
        self.assertFalse(self.panel.review.isEnabled())
        self.assertFalse(self.panel.edit.isEnabled())
        self.assertFalse(self.panel.donor.isEnabled())
        self.panel.set_busy(False)
        self.assertTrue(self.panel.review.isEnabled())
        self.assertFalse(self.panel.build.isEnabled())


if __name__ == "__main__":
    unittest.main()
