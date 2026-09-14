"""Run provider integrity with only WIRING's proposed new pin/count in memory.

This does not change providers.py or claim that integration has happened.
"""
import hashlib
from pathlib import Path
import types
import unittest
from unittest.mock import patch

from mod_editor.core.providers import Nfl2k5UnifiedVisualProvider

ROOT = Path(__file__).resolve().parents[2]


def verify():
    name = 'mod_editor/core/nfl2k5_my_career_prospects.py'
    pins = {**Nfl2k5UnifiedVisualProvider.module_pins,
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()}
    path = ROOT / 'tests/mod_editor/test_provider_integrity.py'
    source = path.read_text()
    old = '[271, 10, 8, 9, 8, 9]'
    if source.count(old) != 1:
        raise ValueError('Historical provider count differs; review integration before this probe.')
    module = types.ModuleType('b69_proposed_provider_integrity')
    module.__file__ = str(path)
    exec(compile(source.replace(old, '[272, 10, 8, 9, 8, 9]'), str(path), 'exec'),
         module.__dict__)
    with patch.object(Nfl2k5UnifiedVisualProvider, 'module_pins', pins):
        return unittest.TextTestRunner(verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromModule(module)).wasSuccessful()


if __name__ == '__main__':
    raise SystemExit(not verify())
