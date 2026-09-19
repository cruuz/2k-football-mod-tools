"""Run the exact Shovel regression against the unmodified base session."""
from pathlib import Path
import subprocess
import sys
import types
import unittest
root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root))
from tests.mod_editor import test_b72_a2_editor_blockers as regression
module = types.ModuleType('mod_editor.apf_studio._b72_shovel_baseline')
module.__package__ = 'mod_editor.apf_studio'
sys.modules[module.__name__] = module
source = subprocess.check_output(['git', 'show', '088e3f41:mod_editor/apf_studio/session.py'], text=True)
exec(compile(source, '<baseline-session>', 'exec'), module.__dict__)
regression.ApfSession = module.ApfSession
regression.SessionError = module.SessionError
suite = unittest.TestSuite([regression.RetailRegressionTests('test_shovel_ol_copies_relay_and_consumed_slot_use_staged_view')])
result = unittest.TestResult()
suite.run(result)
assert len(result.failures) == 1 and not result.errors and not result.skipped
assert 'unexpectedly found' in result.failures[0][1]
print('EXPECTED BASELINE FAILURE: the consumed relay is still offered on 088e3f41.')
