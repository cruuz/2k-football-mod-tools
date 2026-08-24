"""CI-visible runner for tests/nfl2k5_bump_texture_writer_test.py (the developer suite file)."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
TESTS = ROOT / "tests"
if str(TESTS) not in sys.path:
    sys.path.insert(0, str(TESTS))

suite_module = __import__("nfl2k5_bump_texture_writer_test")

if __name__ == "__main__":
    unittest.main(module=suite_module, argv=[sys.argv[0]], exit=True)
