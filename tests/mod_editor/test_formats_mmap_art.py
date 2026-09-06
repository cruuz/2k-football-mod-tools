"""The ``MMAP`` decoder is a shared format package, not a Madden fact.

It was written inside ``mod_editor/games/madden09_ps2`` because Madden NFL 09
was the first module that needed it, and that made it unreachable for every
other game: ``mod_editor/games/_formats/__init__.py`` says *a game imports a
format package; it never imports another game*, so NCAA Football 09's texture
row was filed ``read-only-mapped`` for want of an import.  It now lives in
``mod_editor/games/_formats/mmap_art.py``.

These tests hold the move in place: the shared module stands on its own (it can
be imported without any game package being imported), and the old path still
answers with the same objects so code written against it keeps working.

Synthetic bytes only; no disc, no fixture, no retail file.
"""

from __future__ import annotations

import ast
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.games._formats import mmap_art as shared  # noqa: E402
from mod_editor.games.madden09_ps2 import mmap_art as compat  # noqa: E402


class SharedPackage(unittest.TestCase):
    def test_it_imports_without_importing_a_game(self) -> None:
        """A format package a game may import must not drag a game in with it."""

        program = (
            "import sys\n"
            "from mod_editor.games._formats import mmap_art\n"
            "games = sorted(name for name in sys.modules\n"
            "               if name.startswith('mod_editor.games.')\n"
            "               and not name.startswith('mod_editor.games._formats')\n"
            "               and name != 'mod_editor.games.contract')\n"
            "print(';'.join(games))\n"
        )
        result = subprocess.run([sys.executable, "-c", program], cwd=ROOT,
                                capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "",
                         "importing the shared MMAP decoder imported a game package")

    def test_it_lives_under_formats(self) -> None:
        self.assertEqual(Path(shared.__file__).parent.name, "_formats")

    def test_the_codec_round_trips_on_its_own(self) -> None:
        """Enough of the decoder to prove the shared module is not a stub."""

        payload = bytes(range(256)) * 4 + b"\x00" * 512
        self.assertEqual(shared.lzm1_decompress(shared.lzm1_compress(payload)), payload)
        entries = [(index, 255 - index, index // 2, 128) for index in range(shared.CSM1_ENTRIES)]
        self.assertEqual(shared.deinterleave_csm1(shared.interleave_csm1(entries)), entries)


class CompatibilityImport(unittest.TestCase):
    def test_every_public_name_is_the_shared_object(self) -> None:
        self.assertEqual(compat.__all__, list(shared.__all__))
        for name in shared.__all__:
            with self.subTest(name=name):
                self.assertIs(getattr(compat, name), getattr(shared, name))

    def test_the_two_alpha_helpers_callers_use_are_re_exported(self) -> None:
        # uniform_art and tools/madden09_ps2_texture_identities.py reach for these
        # by name; the shim would be a silent break without them.
        self.assertIs(compat._scale_alpha, shared._scale_alpha)
        self.assertIs(compat._unscale_alpha, shared._unscale_alpha)

    def test_the_shim_carries_no_implementation(self) -> None:
        """A shim that grows code is a second decoder waiting to disagree."""

        tree = ast.parse(Path(compat.__file__).read_text(encoding="utf-8"))
        statements = list(tree.body)
        if statements and isinstance(statements[0], ast.Expr) \
                and isinstance(statements[0].value, ast.Constant):
            statements.pop(0)          # the module docstring
        offenders = [ast.dump(node)[:60] for node in statements
                     if not isinstance(node, (ast.Import, ast.ImportFrom, ast.Assign))]
        self.assertEqual(offenders, [],
                         "the compatibility module has grown something to maintain")


if __name__ == "__main__":
    unittest.main(verbosity=2)
