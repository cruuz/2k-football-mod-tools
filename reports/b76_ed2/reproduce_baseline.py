"""Run the three ed2 regressions against the original call sites, in memory only."""
import ast
import os
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
BASE = '6bd9b3d66d239a267f8d4f66e083b8a6eb320671'


def source(path):
    return subprocess.check_output(['git', 'show', f'{BASE}:{path}'], cwd=ROOT, text=True)


from mod_editor.gui import studio_qt, gameplay_project_ui
from tests.mod_editor import test_b76_ed2_build_recursion as recursion
from tests.mod_editor import test_roster_save_to_disc_wiring as roster


def original_function(path, name, namespace):
    tree = ast.parse(source(path))
    node = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name)
    isolated = dict(namespace)
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(ROOT / path), 'exec'), isolated)
    return isolated[name]


for name in ('_gameplay_build_changed', '_refresh_build_includes'):
    setattr(studio_qt.StudioMainWindow, name, original_function(
        'mod_editor/gui/studio_qt.py', name, vars(studio_qt)))
recursion.observe_build_choices = original_function(
    'mod_editor/gui/gameplay_project_ui.py', 'observe_build_choices', vars(gameplay_project_ui))
roster.proposed_source = lambda: source('mod_editor/gui/roster_editor_panel_qt.py')
suite = unittest.TestSuite([
    recursion.BuildRecursionTests('test_refit_refresh_does_not_reenter_or_lose_authored_settings'),
    roster.WiringTests('test_replacement_roster_from_signed_file_reaches_build_writer'),
    roster.WiringTests('test_private_signed_save_replaces_all_2547_players_through_button'),
])
result = unittest.TextTestRunner(verbosity=2).run(suite)
assert len(result.failures) == 3 and not result.errors and not result.skipped, result
print('PROVED OFFLINE: all three regressions fail on the original call sites as expected.')
