"""Product seam for APF raw-save per-team playbook assignments."""

from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication  # noqa: E402

from mod_editor.apf_studio import save_playbooks as service  # noqa: E402
from mod_editor.apf_studio.save_playbooks_qt import (  # noqa: E402
    SavePlaybookAssignmentsPanel,
)
from tests.test_apf_save_playbook_assignments import synthetic_save  # noqa: E402
from tests.test_apf_save_custom_team_appearance import synthetic_stfs  # noqa: E402
import apf_save_playbook_assignments as low_level  # noqa: E402


class ServiceTests(unittest.TestCase):
    def test_inspection_exposes_all_sided_choices_and_all_team_slots(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "Roster.ROS"
            source.write_bytes(synthetic_save())
            document = service.inspect_save(source)
        self.assertFalse(document.signed_container)
        self.assertTrue(document.write_supported)
        self.assertEqual(len(document.teams), 40)
        self.assertEqual(len(document.playbooks), 69)
        self.assertEqual(len(document.offense), 36)
        self.assertEqual(len(document.defense), 33)
        self.assertIn("source is never changed", document.boundary_message)

    def test_both_assignments_write_to_new_file_and_verify(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "Roster.ROS"
            output = root / "Roster-playbooks.ROS"
            source_payload = synthetic_save()
            source.write_bytes(source_payload)
            document = service.inspect_save(source)
            edit = service.stage_edit(document, 0, 64, 68)
            self.assertIsNotNone(edit)
            receipt = service.write_new_save(document, [edit], output)  # type: ignore[list-item]
            self.assertTrue(receipt.verification_passed)
            self.assertFalse(receipt.runtime_in_game_proved)
            self.assertTrue(receipt.manifest.is_file())
            self.assertEqual(source.read_bytes(), source_payload)
            parsed = low_level.parse_save(output.read_bytes())
            self.assertEqual(parsed.teams[0].offensive_playbook_id, 64)
            self.assertEqual(parsed.teams[0].defensive_playbook_id, 68)

    def test_signed_con_writes_only_a_verified_raw_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "signed.CON"
            source.write_bytes(synthetic_stfs(synthetic_save()))
            document = service.inspect_save(source)
            self.assertTrue(document.signed_container)
            self.assertIn("rehash/resign", document.boundary_message)
            edit = service.PlaybookEdit(0, 64, 68)
            output = root / "Roster-playbooks.ROS"
            receipt = service.write_new_save(document, [edit], output)
            self.assertTrue(receipt.external_reinjection_required)
            self.assertTrue(receipt.output_is_raw_payload)
            self.assertEqual(
                low_level.parse_save(output.read_bytes()).teams[0].offensive_playbook_id,
                64,
            )

    def test_a_save_changed_after_inspection_is_refused_without_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "Roster.ROS"
            output = root / "new.ROS"
            source.write_bytes(synthetic_save())
            document = service.inspect_save(source)
            changed = bytearray(source.read_bytes())
            changed[-1] ^= 1
            source.write_bytes(changed)
            edit = service.PlaybookEdit(0, 64, 68)
            with self.assertRaisesRegex(service.SavePlaybookError, "changed after"):
                service.write_new_save(document, [edit], output)
            self.assertFalse(output.exists())
            self.assertFalse(service.default_manifest_path(output).exists())


class PanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    @staticmethod
    def _immediate_runner(label, operation, on_success=None, blocking=True):
        del label, blocking
        result = operation(lambda *_args: None)
        if on_success is not None:
            on_success(result)
        return True

    def test_raw_save_lists_every_team_and_stages_both_sides(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "Roster.ROS"
            source.write_bytes(synthetic_save())
            panel = SavePlaybookAssignmentsPanel(self._immediate_runner)
            try:
                panel.load_path(source)
                self.application.processEvents()
                self.assertEqual(panel.team_list.count(), 40)
                self.assertEqual(panel.offense.count(), 36)
                self.assertEqual(panel.defense.count(), 33)
                self.assertTrue(panel.stage_button.isEnabled())
                self.assertFalse(panel.write_button.isEnabled())
                panel.offense.setCurrentIndex(panel.offense.findData(64))
                panel.defense.setCurrentIndex(panel.defense.findData(68))
                panel._stage_selected()
                self.assertEqual(panel.stage_count.text(), "1 team staged")
                self.assertTrue(panel.write_button.isEnabled())
                self.assertTrue(panel.team_list.item(0).text().startswith("● "))
            finally:
                panel.deleteLater()
                self.application.processEvents()

    def test_signed_save_lists_assignments_and_explains_disabled_write(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "signed.dat"
            source.write_bytes(synthetic_stfs(synthetic_save()))
            panel = SavePlaybookAssignmentsPanel(self._immediate_runner)
            try:
                panel.load_path(source)
                self.application.processEvents()
                self.assertEqual(panel.team_list.count(), 40)
                self.assertTrue(panel.stage_button.isEnabled())
                self.assertFalse(panel.write_button.isEnabled())
                self.assertIn("STFS", panel.boundary_title.text())
                self.assertIn("rehash/resign", panel.boundary_note.text())
            finally:
                panel.deleteLater()
                self.application.processEvents()

    def test_playbooks_workspace_exposes_the_save_assignment_tab(self) -> None:
        from mod_editor.apf_studio.gui import InspectorCategoryPage
        from mod_editor.apf_studio.models import ApfCategory

        class _Facade:
            pass

        page = InspectorCategoryPage(
            _Facade(),  # type: ignore[arg-type]
            ApfCategory.PLAYBOOKS,
            self._immediate_runner,
            "PLAY and DRCT structural inspector",
            lambda _service: ("Playbook", None),  # type: ignore[arg-type]
        )
        try:
            self.assertIsNotNone(page.workspace_tabs)
            self.assertEqual(
                [
                    page.workspace_tabs.tabText(index)  # type: ignore[union-attr]
                    for index in range(page.workspace_tabs.count())  # type: ignore[union-attr]
                ],
                [
                    "PLAY / DRCT Inspector",
                    # Fine-tune Plays edits which plays a formation offers --
                    # the level below reassigning whole books, which the book
                    # table makes a coarse control.
                    "Fine-tune Plays",
                    "Who lines up",
                    "Assignment Routes",
                    "Save Assignments",
                    "Raw Playbook Assets",
                ],
            )
            self.assertIsInstance(page.save_playbooks, SavePlaybookAssignmentsPanel)
            page.open_workspace("save-playbooks")
            self.assertEqual(page.workspace_tabs.currentIndex(), 4)  # type: ignore[union-attr]
        finally:
            page.deleteLater()
            self.application.processEvents()


class PackagingTests(unittest.TestCase):
    def test_release_allowlist_ships_the_panel_service_and_writer(self) -> None:
        root = Path(__file__).resolve().parents[2]
        lines = {
            line.strip()
            for line in (root / "packaging/apf2k8-release-allowlist.txt")
            .read_text(encoding="utf-8")
            .splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }
        self.assertTrue({
            "mod_editor/apf_studio/save_playbooks.py",
            "mod_editor/apf_studio/save_playbooks_qt.py",
            "tools/apf_save_playbook_assignments.py",
        } <= lines)


if __name__ == "__main__":
    unittest.main()
