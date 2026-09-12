"""Exercise the exact protected Studio proposal in memory, without a display."""
from __future__ import annotations

import ast
import os
from pathlib import Path
import re
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from mod_editor.core.errors import ValidationError


def proposed_source():
    path = "mod_editor/gui/studio_qt.py"
    text = (ROOT / path).read_text(encoding="utf-8")
    if "equipment_choice: tuple[bool, int, str] | None" in text:
        return text  # After integration, exercise the shipped method itself.
    if "equipment_choice: tuple[bool, int] | None" in text:
        return (text.replace("equipment_choice: tuple[bool, int]", "equipment_choice: tuple[bool, int, str]")
                .replace("equipment_choice = (dialog.independent, dialog.scale)",
                         "equipment_choice = (dialog.independent, dialog.scale, dialog.scope)")
                .replace("independent, scale = equipment_choice", "independent, scale, scope = equipment_choice")
                .replace("asset, path, progress, independent=independent, scale=scale,",
                         "asset, path, progress, independent=independent, scale=scale, scope=scope,"))
    source = text.splitlines(True)
    lines = (ROOT / "tests/fixtures/equipment_texture_chain_wiring.patch").read_text(
        encoding="utf-8").splitlines(True)
    assert lines[:2] == [f"--- a/{path}\n", f"+++ b/{path}\n"]
    output, cursor, i = [], 0, 2
    while i < len(lines):
        start = int(re.match(r"@@ -(\d+)", lines[i])[1]) - 1
        assert start >= cursor
        output.extend(source[cursor:start])
        cursor = start
        i += 1
        while i < len(lines) and not lines[i].startswith("@@"):
            line = lines[i]
            if line == "\n":
                line = " \n"
            if line[0] in " -":
                assert source[cursor] == line[1:], (cursor, line)
                cursor += 1
            if line[0] in " +":
                output.append(line[1:])
            i += 1
    return "".join(output + source[cursor:])


class EquipmentWiringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from mod_editor.gui import studio_qt, equipment_texture_import_dialog
        except ImportError as exc:
            raise unittest.SkipTest(f"Offscreen Qt dependencies unavailable: {exc}")
        proposed = proposed_source()
        compile(proposed, "<complete equipment GUI proposal>", "exec")
        owner = next(row for row in ast.parse(proposed).body
                     if isinstance(row, ast.ClassDef) and row.name == "StudioMainWindow")
        method = next(row for row in owner.body
                      if isinstance(row, ast.FunctionDef) and row.name == "_replace_visual_asset")
        cls.namespace = dict(studio_qt.__dict__)
        exec(compile(ast.Module(body=[method], type_ignores=[]),
                     "<equipment import GUI proposal>", "exec"), cls.namespace)
        cls.dialog_module = equipment_texture_import_dialog

    def setUp(self):
        self.asset = SimpleNamespace(asset_id="tset:1:8:0:shoes01", label="Shoe 1",
                                     width=256, height=256, editable=True,
                                     kind="uniform_equipment_texture")
        self.state = SimpleNamespace(category="equipment", selected_asset_id=None, preview=object())
        self.progress = Mock()
        self.result = SimpleNamespace(modified=True, changed_asset_ids=(self.asset.asset_id,),
                                      message="Checked")
        self.facade = SimpleNamespace(replace_equipment_texture=Mock(return_value=self.result),
                                      replace_asset=Mock(return_value=self.result))
        self.draft = SimpleNamespace(source_image=Mock(), native_baseline_png=Mock())
        self.existing = object()
        self.host = SimpleNamespace(
            facade=self.facade, _texture_master_drafts={self.asset.asset_id: self.existing},
            _fit_for_slot=Mock(return_value=Path("fitted.png")),
            _prepare_texture_master_draft=Mock(return_value=self.draft),
            _discard_texture_master_draft=Mock(), _set_status=Mock(),
            _show_error=Mock(), _filter_visual_assets=Mock(),
            _mark_workspace_changed=Mock(), _load_visual_preview=Mock(),
        )

        def start(op, done, **options):
            try:
                result = op(self.progress)
            except ValidationError as exc:
                self.host._show_error(str(exc))
                if options.get("on_error"):
                    options["on_error"](str(exc))
            else:
                done(result)

        self.host._start_task = Mock(side_effect=start)
        self.dialog = SimpleNamespace(exec_=Mock(return_value=self.dialog_module.QDialog.Accepted),
                                      Accepted=self.dialog_module.QDialog.Accepted,
                                      independent=True, scale=4, scope="all-teams")
        replacement = patch.object(self.dialog_module, "EquipmentTextureImportDialog", return_value=self.dialog)
        self.constructor = replacement.start()
        self.addCleanup(replacement.stop)

    def invoke(self):
        self.namespace["_replace_visual_asset"](self.host, self.state, self.asset, Path("authored.png"))

    def test_accepted_explicit_choice_and_fitted_png_reach_preflight(self):
        self.invoke()
        self.facade.replace_equipment_texture.assert_called_once_with(
            self.asset, Path("fitted.png"), self.progress, independent=True, scale=4, scope="all-teams")
        self.facade.replace_asset.assert_not_called()
        self.host._mark_workspace_changed.assert_called_once()
        self.assertIs(self.host._texture_master_drafts[self.asset.asset_id], self.draft)

    def test_default_choice_uses_palette_preflight(self):
        self.dialog.independent, self.dialog.scale = False, 1
        self.invoke()
        self.facade.replace_equipment_texture.assert_called_once_with(
            self.asset, Path("fitted.png"), self.progress, independent=False, scale=1, scope="all-teams")

    def test_cancel_leaves_session_and_authoring_source_untouched(self):
        self.dialog.exec_.return_value = self.dialog_module.QDialog.Rejected
        self.invoke()
        self.host._prepare_texture_master_draft.assert_not_called()
        self.host._start_task.assert_not_called()
        self.host._mark_workspace_changed.assert_not_called()
        self.assertIs(self.host._texture_master_drafts[self.asset.asset_id], self.existing)

    def test_replay_does_not_replace_authoring_source_or_dirty_project(self):
        self.result.changed_asset_ids = ()
        self.invoke()
        self.host._mark_workspace_changed.assert_not_called()
        self.host._discard_texture_master_draft.assert_not_called()
        self.assertIs(self.host._texture_master_drafts[self.asset.asset_id], self.existing)
        self.draft.source_image.unlink.assert_called_once_with(missing_ok=True)
        self.draft.native_baseline_png.unlink.assert_called_once_with(missing_ok=True)

    def test_overflow_cleans_pending_source_and_keeps_previous_master(self):
        self.facade.replace_equipment_texture.side_effect = ValidationError("Artwork cannot fit")
        self.invoke()
        self.host._show_error.assert_called_once_with("Artwork cannot fit")
        self.host._mark_workspace_changed.assert_not_called()
        self.assertIs(self.host._texture_master_drafts[self.asset.asset_id], self.existing)
        self.draft.source_image.unlink.assert_called_once_with(missing_ok=True)
        self.draft.native_baseline_png.unlink.assert_called_once_with(missing_ok=True)

    def test_other_textures_keep_the_existing_import_route(self):
        self.asset.kind = "field_art_texture"
        self.invoke()
        self.constructor.assert_not_called()
        self.facade.replace_equipment_texture.assert_not_called()
        self.facade.replace_asset.assert_called_once_with(self.asset, Path("fitted.png"), self.progress)


if __name__ == "__main__":
    unittest.main()
