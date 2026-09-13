"""Public GUI copy excludes protocol records, exception classes and old release captions."""
from __future__ import annotations
import ast
import os
from pathlib import Path
import re
import sys
import unittest
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.gui.ux_text import plain_error, failure_body

STALE = re.compile(r'\bbeta[ -]6[0-8](?:\.\d+)?\b|\bRC8[0-9]\b', re.I)
DIAGNOSTIC = re.compile(r'\b(?:NFL2K5_)?BUILD_PHASE\b|\b\w*(?:Error|Exception):')

def gui_paths():
    return sorted((ROOT / 'mod_editor/gui').glob('*.py')) + sorted(
        (ROOT / 'mod_editor/apf_studio').glob('*_qt.py')) + [ROOT / 'mod_editor/apf_studio/gui.py']

def public_literals(path):
    tree = ast.parse(path.read_text(encoding='utf-8'))
    excluded = set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.body:
            first = n.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                excluded.add(id(first.value))
        # Diagnostic input recognizers are not user-facing output. No whole-file exemption.
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == 'compile':
            excluded.update(id(c) for c in ast.walk(n))
    return [n for n in ast.walk(tree) if isinstance(n, ast.Constant)
            and isinstance(n.value, str) and id(n) not in excluded]

class StringHygieneTests(unittest.TestCase):
    def test_gui_literals_have_current_copy(self):
        failures = []
        for path in gui_paths():
            for node in public_literals(path):
                if STALE.search(node.value) or DIAGNOSTIC.search(node.value):
                    failures.append(f'{path.relative_to(ROOT)}:{node.lineno}: {node.value[:100]}')
        self.assertEqual(failures, [])

    def test_worker_causes_survive_without_progress_or_class_names(self):
        cases = {
            'ModelsError: Edit both exported files.': 'Edit both exported files.',
            'Nfl2k5BuildError: PermissionError: Choose a writable folder.': 'Choose a writable folder.',
            'NFL2K5_BUILD_PHASE validate_source seconds=0.423\nValueError: Shoe art is too large.': 'Shoe art is too large.',
            'NFL2K5_BUILD_PHASE validate_source seconds=0.423': 'The operation stopped without an explanation.',
            '': 'The operation stopped without an explanation.',
        }
        for value, expected in cases.items():
            with self.subTest(value=value):
                self.assertEqual(plain_error(value), expected)
                body = failure_body(value)
                self.assertIsNone(DIAGNOSTIC.search(body))
                self.assertIn('Your original game disc was not changed.', body)
                self.assertIn('try again', body)

    def test_known_next_step_and_source_scope(self):
        body = failure_body('FileExistsError: output already exists', source_unchanged=False)
        self.assertIn('choose a new filename', body)
        self.assertNotIn('disc was not changed', body)

if __name__ == '__main__':
    unittest.main()
