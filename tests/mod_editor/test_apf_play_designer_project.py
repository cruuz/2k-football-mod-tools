"""APF designer project persistence, atomic staging and rejection paths."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import tempfile
from threading import RLock
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

from test_apf_play_designer import synthetic, play_request
from mod_editor.core.apf2k8_play_designer import empty_plan, compile_design, SELECTOR
from mod_editor.core.errors import ValidationError
from mod_editor.apf_studio import play_design_service as service
from mod_editor.apf_studio.models import ApfSource, Modification
from mod_editor.apf_studio.session import ApfSession
from mod_editor.apf_studio.facade import ApfStudioFacade
from mod_editor.apf_studio.project import load_project, ProjectError


class DesignerProjectTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        index = root / "game" / "0A"
        source = ApfSource(index, index.parent, index, "a" * 64, 1, "b" * 64, "Synthetic APF")
        self.session = ApfSession(source, SimpleNamespace(), cache_root=root / "cache")
        self.body = synthetic()
        self.plan = empty_plan(self.body)
        self.plan["plays"] = [play_request("append", 4, 0, "Portable design")]
        def build(_index, plan):
            result = compile_design(self.body, plan)
            return SimpleNamespace(report={"design": result.report, "resources": []})
        self.patcher = patch.object(service, "build_design", side_effect=build)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def test_stage_undo_save_load_and_apply(self):
        self.session.apply_play_design(self.plan)
        self.assertEqual(self.session.staged_play_design(), self.plan)
        self.session.apply_play_design(self.plan)
        self.assertTrue(self.session.undo())
        self.assertEqual(self.session.modified_count, 0)
        self.session.apply_play_design(self.plan)
        root = Path(self.temp.name)
        path = root / "design.apf2k8mod"
        self.session.save_project(path)
        with zipfile.ZipFile(path) as archive:
            members = [n for n in archive.namelist() if n.startswith("replacements/")]
            self.assertEqual(len(members), 1)
            self.assertTrue(members[0].endswith(".json"))
            self.assertLess(archive.getinfo(members[0]).file_size, 1000)
            self.assertIn(b"Portable design", archive.read(members[0]))
        _, loaded, _ = load_project(path, expected_source_sha256="a" * 64, destination_dir=root / "loaded")
        self.assertEqual(service.read_modification(loaded[0]), self.plan)
        self.session.revert(SELECTOR)
        self.assertEqual(self.session.modified_count, 0)
        self.assertEqual(self.session.load_project(path), 1)
        self.assertEqual(self.session.staged_play_design(), self.plan)
        self.assertTrue(self.session.undo())
        self.assertEqual(self.session.modified_count, 0)

    def test_failed_compile_does_not_stage_or_create_undo(self):
        with patch.object(service, "build_design", side_effect=ValidationError("Allocation full")):
            with self.assertRaisesRegex(ValueError, "Allocation full"):
                self.session.apply_play_design(self.plan)
        self.assertEqual(self.session.modified_count, 0)
        self.assertFalse(self.session.undo())

    def test_facade_invalidates_previous_build_only_after_success(self):
        facade = object.__new__(ApfStudioFacade)
        facade.session = self.session
        facade._session_lock = RLock()
        previous = facade.last_build = object()
        with patch.object(service, "build_design", side_effect=ValidationError("Allocation full")):
            with self.assertRaises(ValueError):
                facade.apply_play_design(self.plan)
        self.assertIs(facade.last_build, previous)
        facade.apply_play_design(self.plan)
        self.assertIsNone(facade.last_build)

    def test_metadata_tampering_is_not_saved(self):
        self.session.apply_play_design(self.plan)
        m = self.session.modifications[0]
        self.session._modifications[SELECTOR] = Modification(m.asset_id, m.kind, m.replacement_path, m.replacement_sha256, {**m.metadata, "source_sha256": "f" * 64})
        with self.assertRaises(ProjectError):
            self.session.save_project(Path(self.temp.name) / "bad.apf2k8mod")

    def test_shared_resource_collision_refuses_atomic_staging(self):
        self.session._modifications["route"] = Modification("route", "play_assignment_route", Path("unused"), "c" * 64, {})
        with self.assertRaisesRegex(ValueError, "owns MASTER"):
            self.session.apply_play_design(self.plan)
        self.assertEqual(self.session.modified_count, 1)


if __name__ == "__main__":
    unittest.main()
