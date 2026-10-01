"""Audit an external ultimate recipe against live Build widgets; no source or build."""
import ast
import importlib.util
import json
import os
from pathlib import Path
import sys
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PyQt5.QtWidgets import QApplication
from mod_editor.gui.build_panel_qt import BuildPanel
spec = importlib.util.spec_from_file_location('coverage', ROOT/'tests/mod_editor/test_ux_build_plan_coverage_qt.py')
coverage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(coverage)
app = QApplication.instance() or QApplication([])
panel = BuildPanel()
source = (ROOT/'mod_editor/gui/build_panel_qt.py').read_text()
tree = ast.parse(source)
plan = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == 'plan')
bindings = {kw.arg: ast.unparse(kw.value) for node in ast.walk(plan) if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute) and node.func.attr == 'BuildPlan' for kw in node.keywords}
for node in ast.walk(plan):
    if isinstance(node, ast.Assign):
        for target in node.targets:
            if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == 'plan':
                bindings[target.attr] = ast.unparse(node.value)
recipe = json.loads(Path(sys.argv[1]).read_text())['overrides']
rows = {}
for key, value in recipe.items():
    if key in panel._boxes():
        box = panel._boxes()[key]
        binding = box.text()
        assert box.accessibleDescription(), key
    else:
        binding = bindings.get(key) or coverage.NOT_A_CONTROL.get(key)
    assert binding, f'No Build binding: {key}'
    rows[key] = dict(binding=binding, value_kind=type(value).__name__,
                     scope='unused optional input' if value is None else 'Build control or paired sub-control')
report = dict(overrides=len(rows), missing=0, fields=rows)
Path(sys.argv[2]).write_text(json.dumps(report, indent=2)+'\n')
print(f'ULTIMATE_BUILD_CONTROLS overrides={len(rows)} missing=0')
