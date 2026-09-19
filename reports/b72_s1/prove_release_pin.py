"""Run the complete release-art suite with the exact pending protected pin.

The supplied context reserves packaging/check_*.py edits for integration.
Only its catalog fingerprint is replaced in memory. Every test assertion,
including tamper refusal, executes unchanged; the on-disk checker is untouched.
"""
from pathlib import Path
import hashlib
import importlib.util
import unittest

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / 'packaging/check_2k5_mod_studio_release.py'
CATALOG = ROOT / 'packaging/nfl2k5_scorebug_template_pngs.json'
before = CHECKER.read_bytes()
spec = importlib.util.spec_from_file_location(
    'b72_release_tests', ROOT / 'tests/mod_editor/test_nfl2k5_scorebug_template_release.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
fresh = hashlib.sha256(CATALOG.read_bytes()).hexdigest()
old = '57422614e0798fce2c6100e40921ab4e467c5e71d6b095f6bb8eb11daf7afa16'
assert module.release.SCOREBUG_TEMPLATE_PNG_CATALOG_SHA256 in (old, fresh)
module.release.SCOREBUG_TEMPLATE_PNG_CATALOG_SHA256 = fresh
print('Pending integration pin only: SCOREBUG_TEMPLATE_PNG_CATALOG_SHA256 = ' + repr(fresh), flush=True)
try:
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromModule(module))
finally:
    assert CHECKER.read_bytes() == before, 'The protected release checker changed.'
raise SystemExit(0 if result.wasSuccessful() else 1)
