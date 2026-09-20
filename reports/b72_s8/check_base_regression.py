"""Prove the stale-event regression rejects the exact base owner bytes."""
from pathlib import Path
import json
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_scorebug_sprite_code as engine
from tests.mod_editor.test_nfl2k5_scorebug_down_visibility import DownVisibilityTests

baseline = {}
exec(subprocess.check_output(['git', 'show',
    'c5134e232:mod_editor/core/nfl2k5_scorebug_sprite_code.py'], cwd=ROOT), baseline)
with patch.multiple(engine, **{k:baseline[k] for k in ('CODE','RELOCATIONS','LABELS')}):
    result = unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite([
        DownVisibilityTests('test_real_draw_gate_not_pending_requests')]))
assert len(result.failures) == 1 and not result.errors and not result.skipped
assert "AssertionError: True != False" in result.failures[0][1]
Path(__file__).with_name('base_regression.json').write_text(json.dumps(dict(
    base='c5134e232', expected_failure=True, test='test_real_draw_gate_not_pending_requests',
    reason='Base owner leaves the seeded inactive event plate visible.'), indent=2)+'\n')
print('Expected base failure observed; the regression rejects the unfixed owner.')
