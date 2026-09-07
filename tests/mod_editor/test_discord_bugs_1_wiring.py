"""PROVED proposal tests for protected call sites, executed only in memory.

ASTRA_TEST_UNWIRED=1 runs the same checks on untouched product code to retain
failing repro evidence. Default mode tests the exact WIRING patch, not a claim
that its protected integrations have landed. Plain standalone unittest.
"""
from contextlib import ExitStack
import importlib
import os
from pathlib import Path
import re
import sys
import tempfile
import types
import unittest
from unittest.mock import patch, Mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt5.QtWidgets import QApplication


def proposed_sources():
    """Apply exact unified hunks without git, shell tools, or filesystem writes."""
    lines = (ROOT / "tests/fixtures/discord_bugs_1_wiring.patch").read_text().splitlines(True)
    result = {}
    i = 0
    while i < len(lines):
        assert lines[i].startswith("--- a/")
        path = lines[i][6:].strip()
        assert lines[i + 1].strip() == "+++ b/" + path
        original = (ROOT / path).read_text().splitlines(True)
        output, cursor = [], 0
        i += 2
        while i < len(lines) and lines[i].startswith("@@"):
            match = re.match(r"@@ -(\d+)(?:,\d+)? \+\d+(?:,\d+)? @@", lines[i])
            start = int(match[1]) - 1
            assert start >= cursor
            output += original[cursor:start]
            cursor = start
            i += 1
            while i < len(lines) and not lines[i].startswith(("@@", "--- a/")):
                line = lines[i]
                # Unified diffs may suppress the prefix on empty context lines.
                if line == "\n":
                    line = " \n"
                if line[0] in " -":
                    assert original[cursor] == line[1:], (path, cursor, line)
                    cursor += 1
                if line[0] in " +":
                    output.append(line[1:])
                i += 1
        result[path] = "".join(output + original[cursor:])
    return result


def install_proposal(stack):
    if os.environ.get("ASTRA_TEST_UNWIRED") == "1":
        return
    for path, source in proposed_sources().items():
        name = path[:-3].replace("/", ".")
        original = importlib.import_module(name)
        module = types.ModuleType(name)
        module.__file__ = str(ROOT / path)
        module.__package__ = name.rsplit(".", 1)[0]
        parent = importlib.import_module(module.__package__)
        stack.enter_context(patch.dict(sys.modules, {name: module}))
        stack.enter_context(patch.object(parent, name.rsplit(".", 1)[1], module))
        exec(compile(source, module.__file__, "exec"), module.__dict__)


class WiringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.stack = ExitStack()
        cls.addClassCleanup(cls.stack.close)
        install_proposal(cls.stack)

    def setUp(self):
        from mod_editor.gui.build_panel_qt import BuildPanel
        from mod_editor.gui.gameplay_patches_panel_qt import GameplayPatchesPanel
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.source = self.root / "source.iso"
        self.source.write_bytes(b"unchanged synthetic image")
        self.build = BuildPanel()
        self.gameplay = GameplayPatchesPanel()
        state = {"path": str(self.source), "container": "xiso", "momentum_settings": {"status": "retail"},
                 **{k: "retail" for k in self.build._boxes()}, **{k: "retail" for k in self.gameplay.checks}}
        self.build.apply_state(state)
        self.gameplay.apply_state(state)
        self.build.target_field.setText(str(self.root / "target.iso"))
        self.addCleanup(self.cleanup_panels)

    def cleanup_panels(self):
        self.build._hires_budget_timer.stop()
        self.build.deleteLater()
        self.gameplay.deleteLater()
        self.app.processEvents()

    def test_B3_PROVED_installed_RC_alias_is_not_offered_again(self):
        from mod_editor.core import update_check
        for tag, label in (("beta-57", "v1.0-RC81"), ("beta-61", "1.0.0rc85"), ("beta-62", "RC86")):
            with self.subTest(label=label):
                self.assertFalse(update_check._is_newer(tag, label))
                self.assertFalse(update_check._is_newer("beta-56", label))
                self.assertTrue(update_check._is_newer("beta-63", label))

    def test_B7_PROVED_duplicate_checkbox_is_one_plan_and_one_writer_call(self):
        from mod_editor.core import mod_build
        self.gameplay.checks["catch_slider"].setChecked(True)
        self.build.catch_check.setChecked(True)
        self.assertEqual(self.gameplay.plan().catch_slider, self.build.plan().catch_slider)
        with patch.object(mod_build.tt, "write_copy", return_value={"changed_byte_count": 1}) as write, \
             patch.object(mod_build, "inspect", return_value={}):
            receipt = mod_build._build(self.build.plan())
        self.assertEqual(write.call_count, 1)
        self.assertTrue(write.call_args.kwargs["catch_slider"])
        self.assertEqual([step["step"] for step in receipt["steps"]], ["xbe"])

    def test_B9_PROVED_unchanged_copy_cannot_claim_changes_written(self):
        from mod_editor.core import mod_build
        from mod_editor.core.build_feedback import completion
        target = self.root / "copy.iso"
        with patch.object(mod_build, "inspect", return_value={}):
            result = mod_build.build(mod_build.BuildPlan(str(self.source), str(target)))
        self.assertEqual(result["outcome"]["status"], "unchanged")
        self.assertEqual(completion(result)[0], "No changes written")
        self.assertEqual(target.read_bytes(), self.source.read_bytes())
        self.assertFalse(list(self.root.glob(".studio-build-*")))

    def test_B22_PROVED_restore_all_gameplay_flags_and_levels(self):
        state = {"catch_slider": True, "dynamic_kickoff": True, "momentum": 50,
                 "screen_timing": "B", "abilities": True, "abilities_off_week": 5,
                 "uniform_choice": "rule", "throw": True, "max_deep_yards": 75.0, "arc": .2}
        self.build.restore_project_build_settings(state)
        restored = self.build.project_build_settings()
        for key, value in state.items():
            self.assertEqual(restored[key], value, key)
        self.build.restore_project_build_settings({})
        self.assertFalse(self.build.plan().catch_slider)
        self.assertIsNone(self.build.plan().screen_timing)

    def test_B22_PROVED_synchronization_and_forwarding_survive_restore(self):
        from mod_editor.gui.studio_qt import StudioMainWindow
        host = types.SimpleNamespace(_build_panel=self.build, _gameplay_patches_panel=self.gameplay,
                                     _restoring_music_playlist=False, _gameplay_build_changed=Mock())
        StudioMainWindow._connect_gameplay_build(host)
        self.gameplay.checks["catch_slider"].setChecked(True)
        self.assertTrue(self.build.plan().catch_slider)
        self.build.catch_check.setChecked(False)
        self.assertFalse(self.gameplay.plan().catch_slider)
        # The restore refresh must not write partial choices back to the session.
        host._restoring_music_playlist = True
        self.build.restore_project_build_settings({"dynamic_kickoff": True})
        host._gameplay_build_link.refresh_from_build()
        self.assertTrue(self.gameplay.plan().dynamic_kickoff)

    def test_B22_PROVED_footer_routes_gameplay_to_the_combined_build(self):
        from mod_editor.gui.studio_qt import StudioMainWindow
        self.build.catch_check.setChecked(True)
        host = types.SimpleNamespace(_build_panel=self.build, _capture_music_build_settings=Mock(), _set_status=Mock())
        with patch.object(self.build, "blocker", return_value=""), patch.object(self.build, "_build") as build:
            StudioMainWindow._choose_build_output(host)
        build.assert_called_once()
        host._capture_music_build_settings.assert_called_once()

    def test_B12_PROVED_shared_portrait_edits_are_included_without_naming_or_music(self):
        self.build._facade = types.SimpleNamespace(_session=object(), modified_count=1)
        self.build.catch_check.setChecked(True)
        self.assertTrue(self.build._include_session_project())

    def test_B22_PROVED_combined_build_patches_the_staged_art_once(self):
        from dataclasses import dataclass
        import threading
        from mod_editor.core import mod_build
        @dataclass
        class StageResult:
            edit_count: int = 1
        staged_sources = []
        def stage(cache, session, target, progress):
            target.write_bytes(self.source.read_bytes() + b"portrait")
            return StageResult()
        def write(source, target, **kwargs):
            staged_sources.append(Path(source).read_bytes())
            Path(target).write_bytes(staged_sources[-1] + b"catch patch")
            return {"changed_byte_count": 11}
        self.build._facade = types.SimpleNamespace(
            _lock=threading.RLock(), _cache=object(), _session=object(), source_path=self.source,
            source_ready=True, modified_count=1, build_service=types.SimpleNamespace(build=stage))
        self.build.catch_check.setChecked(True)
        plan = self.build.plan()
        with patch.object(mod_build.tt, "write_copy", side_effect=write), patch.object(mod_build, "inspect", return_value={}):
            receipt = self.build._build_operation(plan, lambda *args: None, include_session=True)
        self.assertEqual(staged_sources, [self.source.read_bytes() + b"portrait"])
        self.assertTrue(Path(plan.target).read_bytes().endswith(b"portraitcatch patch"))
        self.assertEqual(receipt["outcome"]["status"], "changed")
        self.assertEqual([step["step"] for step in receipt["steps"]], ["shared_project", "xbe"])
        self.assertFalse(list(self.root.glob(".shared-build-*")))

    def test_B22_PROVED_failed_combined_build_does_not_publish_partial_art(self):
        from mod_editor.core import mod_build
        target = self.root / "already.iso"
        target.write_bytes(b"keep existing build")
        def fail(plan, *args, **kwargs):
            Path(plan.target).write_bytes(b"partial patch")
            raise ValueError("injected patch failure")
        with patch.object(mod_build, "_build", side_effect=fail), patch.object(mod_build, "_with_identity", side_effect=lambda exc, *args: exc):
            with self.assertRaisesRegex(ValueError, "injected"):
                mod_build.build(mod_build.BuildPlan(str(self.source), str(target), overwrite=True))
        self.assertEqual(target.read_bytes(), b"keep existing build")
        self.assertFalse(list(self.root.glob(".studio-build-*")))

    def test_B17_PROVED_existing_disabled_build_reason_names_next_step(self):
        from mod_editor.gui.studio_qt import _build_blocker_message
        self.assertIn("Open your game disc", _build_blocker_message(ready=False, edit_count=0, busy=False))
        self.assertIn("at least one project edit", _build_blocker_message(ready=True, edit_count=0, busy=False))
        self.assertIn("Wait", _build_blocker_message(ready=True, edit_count=1, busy=True))


if __name__ == "__main__":
    unittest.main()
