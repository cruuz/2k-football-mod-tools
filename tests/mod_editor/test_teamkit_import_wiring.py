"""Execute the protected Team Kit GUI proposal in memory, never on disk."""
from __future__ import annotations

import ast
import os
from pathlib import Path
import re
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from mod_editor.core.errors import ValidationError
from mod_editor.studio.uniform_bundle import TeamKitBundleImportResult, TeamKitComponentImport


def proposed_source():
    path = "mod_editor/gui/studio_qt.py"
    text = (ROOT / path).read_text(encoding="utf-8")
    if "def _show_team_kit_import_result(" in text and "def _team_kit_import_selectors(" in text:
        return text  # the proposal is wired on this stack: execute the shipped source itself
    source = text.splitlines(True)
    lines = (ROOT / "tests/fixtures/discord_teamkit_import_wiring.patch").read_text(encoding="utf-8").splitlines(True)
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
            if line[0] in " +": output.append(line[1:])
            i += 1
    return "".join(output + source[cursor:])


class TeamKitImportWiringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from mod_editor.gui import studio_qt
        except ImportError as exc:
            raise unittest.SkipTest(f"Offscreen Qt dependencies unavailable: {exc}")
        tree = ast.parse(proposed_source())
        owner = next(row for row in tree.body if isinstance(row, ast.ClassDef)
                     and row.name == "StudioMainWindow")
        names = {"_team_kit_import_selectors", "_show_team_kit_import_result",
                 "_choose_team_kit_import", "_choose_digit_sheet_import"}
        cls.namespace = dict(studio_qt.__dict__)
        exec(compile(ast.Module(body=[row for row in owner.body
                                     if isinstance(row, ast.FunctionDef) and row.name in names],
                                type_ignores=[]), "<Team Kit GUI proposal>", "exec"), cls.namespace)

    def setUp(self):
        self.ns = self.namespace
        self.box = Mock()
        self.ns["QMessageBox"] = Mock(return_value=self.box)

    def result(self, changed=1):
        return TeamKitBundleImportResult(
            Path("kit"), ("02H3",), 2, changed, 1, None,
            "Imported: 1. Skipped unchanged: 1. Overwritten: 1. Your source XISO was not changed.",
            (TeamKitComponentImport("torso", "02H3", "Torso / Jersey", "Live Uniform",
                                    "imported", "your earlier edit", True),
             TeamKitComponentImport("digit", "02H3", "Digit 0", "Jersey Digits", "skipped_unchanged")),
        )

    def test_dialog_and_panel_use_identical_counts_and_component_receipt(self):
        result = self.result()
        host = SimpleNamespace(_set_status=Mock(), team_kit_receipt_summary=Mock())
        self.ns["_show_team_kit_import_result"](host, result, "Team Kit import complete")
        self.box.setText.assert_called_once_with(result.message)
        self.box.setDetailedText.assert_called_once_with(result.details)
        host.team_kit_receipt_summary.setText.assert_called_once_with(result.summary)
        host.team_kit_receipt_summary.setToolTip.assert_called_once_with(result.details)
        self.assertIn("replaced your earlier edit", result.details)

    def test_selected_team_style_and_sides_reach_facade_and_only_changes_mark_dirty(self):
        for changed in (0, 1):
            with self.subTest(changed=changed):
                result = self.result(changed)
                facade = SimpleNamespace(source_ready=True, import_team_kit=Mock(return_value=result))
                host = SimpleNamespace(
                    facade=facade, _team_kit_import_selectors=lambda: ("02H3", "02A3"),
                    team_kit_container=SimpleNamespace(currentData=lambda: "folder"),
                    _set_status=Mock(), _selected_asset=None,
                    _mark_workspace_changed=Mock(), _refresh_edit_state=Mock(),
                    team_kit_imported=SimpleNamespace(emit=Mock()),
                    _show_team_kit_import_result=Mock(),
                    _start_task=lambda op, done, **kw: done(op(lambda *_: None)),
                )
                self.ns["QFileDialog"] = SimpleNamespace(getExistingDirectory=lambda *a: "kit")
                self.ns["_choose_team_kit_import"](host)
                self.assertEqual(facade.import_team_kit.call_args.kwargs["expected_set_selectors"],
                                 ("02H3", "02A3"))
                self.assertEqual(host._mark_workspace_changed.call_count, changed)
                host.team_kit_imported.emit.assert_called_once_with(changed)
                host._show_team_kit_import_result.assert_called_once_with(result, "Team Kit import complete")

    def test_selection_resolves_exact_physical_sets_and_requires_selected_team(self):
        host = SimpleNamespace(
            _selected_set=SimpleNamespace(asset_code="02", variant=3),
            team_kit_scope=SimpleNamespace(currentData=lambda: "BOTH"),
            uniform_catalog=SimpleNamespace(uniform_set_for=lambda code, side, style:
                SimpleNamespace(selector=f"{code}{side[0]}{style}")),
        )
        self.assertEqual(self.ns["_team_kit_import_selectors"](host), ("02H3", "02A3"))
        host._selected_set = None
        with self.assertRaisesRegex(ValidationError, "Choose a team"):
            self.ns["_team_kit_import_selectors"](host)


if __name__ == "__main__":
    unittest.main()
