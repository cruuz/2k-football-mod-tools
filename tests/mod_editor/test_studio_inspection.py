"""The real child inspection preserves Build's typed throw settings."""
from pathlib import Path
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


if __name__ == '__main__':
    unittest.main()
