"""Raw-save book identity: exact writes, no overwrite, and explicit Qt consent."""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from mod_editor.apf_studio import save_playbooks as service
from mod_editor.core import apf2k8_book_identity as identity
from mod_editor.core.errors import ValidationError
from tests.mod_editor.test_apf_ps3_roster_convert import Fixture

FIXTURE = Path(os.environ.get("APF_ROSTER_ROS", "/home/noah/Downloads/apfe/Roster.ROS"))


class WriterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = Fixture().expected()

    def test_interned_string_is_reused_and_only_one_label_changes(self):
        before = identity.parse_roster_identity(self.source, raw_save=True)
        output, receipt = identity.rewrite_save_label_type(self.source, 0, "Book")
        after = identity.parse_roster_identity(output, raw_save=True)
        self.assertEqual(after.teams, before.teams)
        self.assertEqual(after.labels[1:], before.labels[1:])
        self.assertEqual(after.labels[0].kind, "Book")
        changed = [i for i, (a, b) in enumerate(zip(self.source, output)) if a != b]
        self.assertEqual(changed, receipt["changed_offsets"])
        self.assertTrue(set(changed) <= set(range(before.labels[0].offset + 4, before.labels[0].offset + 8)))
        self.assertTrue(identity.verify_save_label_type(self.source, output, receipt)["verified"])
        restored, _ = identity.rewrite_save_label_type(output, 0, before.labels[0].kind)
        self.assertEqual(restored, self.source)
        self.assertFalse(receipt["runtime_in_game_proved"])
        self.assertIn("UNWITNESSED", receipt["runtime_status"])

    def test_invalid_missing_unchanged_and_unsupported_inputs_refuse(self):
        for label, kind in [(True, "Book"), (69, "Book"), (0, "../Book"), (0, "B" * 28),
                            (0, "Missing Clone"), (0, "O")]:
            with self.subTest(label=label, kind=kind), self.assertRaises(ValidationError):
                identity.rewrite_save_label_type(self.source, label, kind)
        with self.assertRaisesRegex(ValidationError, "season saves"):
            identity.rewrite_save_label_type(self.source + bytes(70448), 0, "Book")

    def test_verifier_rejects_unrelated_byte_and_receipt_tampering(self):
        output, receipt = identity.rewrite_save_label_type(self.source, 0, "Book")
        forged = bytearray(output)
        forged[-1] ^= 1
        with self.assertRaises(ValidationError):
            identity.verify_save_label_type(self.source, bytes(forged), receipt)
        forged_receipt = copy.deepcopy(receipt)
        forged_receipt["changed_offsets"] = []
        with self.assertRaises(ValidationError):
            identity.verify_save_label_type(self.source, output, forged_receipt)

    @unittest.skipUnless(FIXTURE.is_file(), f"Raw Roster.ROS fixture absent: {FIXTURE}")
    def test_fixture_ros_round_trip(self):
        source = FIXTURE.read_bytes()
        before = identity.parse_roster_identity(source, raw_save=True)
        output, receipt = identity.rewrite_save_label_type(source, 0, before.labels[0].name)
        self.assertEqual(len(output), len(source))
        self.assertTrue(identity.verify_save_label_type(source, output, receipt)["verified"])
        restored, _ = identity.rewrite_save_label_type(output, 0, before.labels[0].kind)
        self.assertEqual(restored, source)
        self.assertEqual(FIXTURE.read_bytes(), source)
        self.assertEqual(receipt["filename_id"], identity.filename_id(before.labels[0].name))


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="apf-label-type-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "Roster.ROS"
        self.source.write_bytes(Fixture().expected())
        self.document = service.inspect_save(self.source)
        self.output = self.root / "New roster.ROS"
        self.index = self.root / "Built game" / "0A"

    def game(self, *, types=("Book",), name="Book"):
        from contextlib import ExitStack
        stack = ExitStack()
        stack.enter_context(patch.object(service, "built_label_types", return_value=types))
        resource = stack.enter_context(patch.object(identity, "read_resource",
            return_value=(None, SimpleNamespace(table_index=77), None, b"synthetic book", None, None)))
        stack.enter_context(patch.object(identity.splb, "parse_book", return_value=SimpleNamespace(name=name)))
        return stack, resource

    def test_new_file_receipt_and_hash_owned_resource_lookup(self):
        context, resource = self.game()
        with context:
            receipt = service.write_label_type(self.document, 0, "Book", self.index, self.output)
        resource.assert_called_with(self.index, identity.filename_id("Book"), "spb", "SPLB")
        self.assertEqual(hashlib.sha256(self.source.read_bytes()).hexdigest(), self.document.source_sha256)
        saved = json.loads(Path(receipt["manifest"]).read_text())
        identity.verify_save_label_type(self.document.raw_payload, self.output.read_bytes(), saved)

    def test_wrong_side_or_header_refuses_before_output(self):
        for options in ({"types": ("OTHER",)}, {"name": "WRONG"}):
            context, _ = self.game(**options)
            with context, self.assertRaises(service.SavePlaybookError):
                service.write_label_type(self.document, 0, "Book", self.index, self.output)
            self.assertFalse(self.output.exists())

    def test_source_change_alias_and_existing_receipt_are_preserved(self):
        with self.assertRaisesRegex(service.SavePlaybookError, "separate"):
            service.write_label_type(self.document, 0, "Book", self.index, self.source)
        manifest = self.output.with_name(self.output.name + ".label-type.json")
        manifest.write_bytes(b"keep")
        context, _ = self.game()
        with context, self.assertRaises(service.SavePlaybookError):
            service.write_label_type(self.document, 0, "Book", self.index, self.output)
        self.assertFalse(self.output.exists())
        self.assertEqual(manifest.read_bytes(), b"keep")
        self.output.write_bytes(b"existing")
        context, _ = self.game()
        with context, self.assertRaises(service.SavePlaybookError):
            service.write_label_type(self.document, 0, "Book", self.index, self.output)
        self.assertEqual(self.output.read_bytes(), b"existing")
        self.source.write_bytes(b"changed")
        with self.assertRaisesRegex(service.SavePlaybookError, "changed after"):
            service.write_label_type(self.document, 0, "Book", self.index, self.output)


class PanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PyQt5.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_cancel_creates_nothing_and_yes_runs_write(self):
        from mod_editor.apf_studio import save_playbooks_qt as qt
        from tests.test_apf_save_playbook_assignments import synthetic_save
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "Roster.ROS"
            source.write_bytes(synthetic_save())
            def run(_label, operation, on_success, _blocking):
                result = operation(lambda *_: None)
                on_success(result)
            panel = qt.SavePlaybookAssignmentsPanel(run)
            try:
                panel.load_path(source)
                self.assertTrue(panel.label_type_button.isEnabled())
                label = panel.document.playbooks[0]
                selection = f"00: {label.name} ({label.side}, {label.kind})"
                receipt = {"affected_team_indices": [0, 36], "output": "new.ROS", "manifest": "new.json",
                           "changed_byte_count": 2, "runtime_status": "UNWITNESSED"}
                for answer in (qt.QMessageBox.No, qt.QMessageBox.Yes):
                    with patch.object(qt.QInputDialog, "getItem", side_effect=[(selection, True), ("Book", True)]), \
                         patch.object(qt.QFileDialog, "getOpenFileName", return_value=("built/0A", "")), \
                         patch.object(qt.QFileDialog, "getSaveFileName", return_value=("new.ROS", "")), \
                         patch.object(qt, "built_label_types", return_value=("Book",)), \
                         patch.object(qt, "prepare_label_type", return_value=(b"", receipt)), \
                         patch.object(qt.QMessageBox, "question", return_value=answer) as confirm, \
                         patch.object(qt.QMessageBox, "information"), \
                         patch.object(qt, "write_label_type", return_value=receipt) as write:
                        panel.label_type_button.click()
                        self.assertEqual(write.call_count, int(answer == qt.QMessageBox.Yes))
                        self.assertIn("UNWITNESSED", confirm.call_args.args[2])
                        self.assertEqual(confirm.call_args.args[-1], qt.QMessageBox.No)
                panel.staged[0] = service.PlaybookEdit(0, 1, 32)
                panel._update_enabled()
                self.assertFalse(panel.label_type_button.isEnabled())
            finally:
                panel.deleteLater()
                self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
