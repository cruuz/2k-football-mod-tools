"""Conformance for the NFL Street 3 (USA, PlayStation 2) game module.  No game data.

The generic harness proves the module on its own synthetic sources; the
fragment check proves the committed mirrors agree with the canonical registry
and allowlist once the game's rows and files are in them.
"""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import mod_editor.games as games  # noqa: E402
from mod_editor.games import conformance, fragments  # noqa: E402

GAME_ID = "nflstreet3_ps2"


class Nflstreet3Ps2ModuleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.work = Path(tempfile.mkdtemp(prefix=f"{GAME_ID}-conformance-"))
        self.addCleanup(shutil.rmtree, self.work, True)

    def test_the_module_conforms(self) -> None:
        game = games.load(GAME_ID)
        result = conformance.run(game, self.work)
        self.assertTrue(result.passed, "\n".join(check.line() for check in result.failures))

    def test_fragments_match_the_canonical_files(self) -> None:
        self.assertEqual(fragments.check(GAME_ID), [])


if __name__ == "__main__":
    unittest.main()
