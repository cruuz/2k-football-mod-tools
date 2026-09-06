"""The NFL 2K5 (PS2) executable-patch lane reads the host's catalogue as the host stores it.

Since Beta 61 an entry of the host's ``PATCHES`` tuple may quote another module's
constant for its on-screen words; the reader must still see every entry's key and
title, and must still refuse when the catalogue is gone.
"""

import ast
import pathlib
import tempfile
import unittest

from mod_editor.games.contract import Refusal
from mod_editor.games.nfl2k5_ps2 import code_patches


SOURCE = '''
import mod_editor.core.throw_tuning as tt
PATCHES = (
    ("catch_strength", "Catch strength", "the host's words"),
    ("defensive_try", "Defensive try", tt.defensive_try_patch.UI_TEXT),
)
TEXT_PATCHES = ()
STRING_TOGGLES = {}
'''


class HostCatalogueTests(unittest.TestCase):
    def test_module_constant_in_an_entry_is_read_as_its_text(self):
        tree = ast.parse(SOURCE)
        rows = code_patches._literal(tree, "PATCHES", pathlib.Path("panel.py"), SOURCE)
        self.assertEqual([row[0] for row in rows], ["catch_strength", "defensive_try"])
        self.assertEqual(rows[0][2], "the host's words")
        self.assertEqual(rows[1][2], "tt.defensive_try_patch.UI_TEXT")

    def test_pure_literals_still_evaluate(self):
        tree = ast.parse("PATCHES = (('a', 'A', 'x'),)\n")
        self.assertEqual(code_patches._literal(tree, "PATCHES", pathlib.Path("panel.py")), (("a", "A", "x"),))

    def test_missing_catalogue_still_refuses(self):
        tree = ast.parse("OTHER = 1\n")
        with self.assertRaises(Refusal):
            code_patches._literal(tree, "PATCHES", pathlib.Path("panel.py"), "OTHER = 1\n")

    def test_the_real_host_catalogue_reads(self):
        rows = code_patches.host_patches()
        self.assertGreaterEqual(len(rows), 30)
        self.assertEqual(len({row.patch_id for row in rows}), len(rows))


if __name__ == "__main__":
    unittest.main()
