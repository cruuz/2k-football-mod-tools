#!/usr/bin/env python3
"""Run the source-free APF TXT/STRG writer and product integration tests."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromNames(
        (
            "tests.test_apf_txt_loc_patch",
            "tests.mod_editor.test_apf_studio_text_edit",
        )
    )
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
