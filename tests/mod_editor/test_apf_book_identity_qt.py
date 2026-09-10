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
        self.assertFalse(self.panel.team.isEnabled())

    def test_preset_publication_is_bound_to_the_reviewed_reports(self):
        self.load()
        self.panel.action.setCurrentIndex(1)
        report = {"book_identity": self.report, "source_sha256": "synthetic"}
        class Preset:
            pass
        result = Preset()
        result.report = report
        with patch("mod_editor.apf_studio.book_identity_qt.presets.compile_preset", return_value=result):
            self.panel.review_selection()
        with patch("mod_editor.apf_studio.book_identity_qt.presets.build_presets_folder",
                   return_value={"runtime_status": "UNWITNESSED"}) as build_mock:
            self.panel.build_to(Path("synthetic-output"))
        self.assertEqual(build_mock.call_args.kwargs["expected_reports"], [report])
        self.assertIn("UNWITNESSED", self.panel.status.text())
        self.assertFalse(self.panel.build.isEnabled())


if __name__ == "__main__":
    unittest.main()
