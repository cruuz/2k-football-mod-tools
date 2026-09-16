"""C4 lighting composes with the combined scorebug/widescreen test-disc XBE owners."""
from pathlib import Path
import itertools
import os
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_modern_color as colour
from mod_editor.core import nfl2k5_scorebug_runtime as scorebug
from mod_editor.core import nfl2k5_widescreen as wide
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest

XBE = Path(os.environ.get('NFL2K5_RETAIL_EXTRACTION', '/media/noah/Storage/for codex 1.0/extracted')) / 'ESPN NFL 2K5 (USA)/default.xbe'


@unittest.skipUnless(XBE.is_file(), 'retail USA executable unavailable')
class DaylightCompositionTests(unittest.TestCase):
    def test_all_orders_preserve_peers_replay_and_independent_colour_restore(self):
        base = space.apply(XBE.read_bytes(), scorebug.REQUESTS)[0]
        expected = None
        for order in itertools.permutations((colour, scorebug, wide)):
            with self.subTest(order=[m.__name__ for m in order]):
                after = base
                for owner in order:
                    after = owner.apply(after)[0]
                if expected is None:
                    expected = after
                self.assertEqual(after, expected)
                for owner in order:
                    self.assertEqual(owner.status(after), 'applied')
                    self.assertEqual(owner.apply(after)[0], after)
                restored = colour.apply(after, enabled=False)[0]
                self.assertEqual(colour.status(restored), 'retail')
                self.assertEqual(scorebug.status(restored), 'applied')
                self.assertEqual(wide.status(restored), 'applied')
                self.assertEqual(colour.apply(restored)[0], after)
                for section in _sections(after):
                    self.assertEqual(section.stored_digest, section_digest(after, section))


if __name__ == '__main__':
    unittest.main(verbosity=2)
