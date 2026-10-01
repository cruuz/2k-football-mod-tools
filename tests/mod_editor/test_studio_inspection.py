"""The real child inspection preserves Build's typed throw settings."""
from pathlib import Path
import contextlib
import io
import sys
import tempfile
import unittest
from unittest.mock import patch
import subprocess

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
from mod_editor.core import mod_build, studio_inspection
from mod_editor.core.nfl2k5_throw_tuning import TuningSettings
from nfl2k5_throw_tuning_test import _build_synthetic_xbe


class InspectionTests(unittest.TestCase):
    def test_real_child_matches_in_process_synthetic_inspection(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'synthetic.xbe'
            original = _build_synthetic_xbe()
            source.write_bytes(original)
            expected = mod_build.inspect(source)
            result = studio_inspection.inspect_source(source)
            self.assertEqual(result, expected)
            self.assertIsInstance(result['throw'], TuningSettings)
            self.assertEqual(source.read_bytes(), original)

    def test_bad_child_results_and_errors_propagate(self):
        for result in (subprocess.CompletedProcess([], 1, '', 'synthetic inspection failure'),
                       subprocess.CompletedProcess([], 0, '[]', ''),
                       subprocess.CompletedProcess([], 0, 'truncated', '')):
            with self.subTest(result=result), patch.object(subprocess, 'run', return_value=result):
                with self.assertRaises(ValueError):
                    studio_inspection.inspect_source(Path('synthetic.xbe'))

    def test_selected_marks_reach_child_and_are_scoped_during_inspection(self):
        from mod_editor.core import nfl2k5_official_marks as marks
        selected = '/portable sources/marks'
        result = subprocess.CompletedProcess([], 0, '{}', '')
        with patch.object(subprocess, 'run', return_value=result) as run:
            studio_inspection.inspect_source(Path('synthetic.xbe'), marks_pack=selected)
        child_selected = run.call_args.args[0][-1]
        self.assertEqual(Path(child_selected).absolute(), Path(selected).absolute())
        previous = marks.selected_root()
        def inspect(source):
            self.assertEqual(marks.selected_root(), child_selected)
            return {'throw': TuningSettings()}
        with patch.object(mod_build, 'inspect', side_effect=inspect), contextlib.redirect_stdout(io.StringIO()):
            studio_inspection._main('synthetic.xbe', child_selected)
        self.assertEqual(marks.selected_root(), previous)

    def test_child_launch_does_not_require_resolve(self):
        result = subprocess.CompletedProcess([], 0, '{}', '')
        with patch.object(Path, 'resolve', side_effect=OSError(234, 'More data available')), \
             patch.object(subprocess, 'run', return_value=result) as run:
            self.assertEqual(studio_inspection.inspect_source(Path('user sources é/disc.iso')), {})
        self.assertEqual(Path(run.call_args.args[0][-2]).name, 'disc.iso')


if __name__ == '__main__':
    unittest.main()
