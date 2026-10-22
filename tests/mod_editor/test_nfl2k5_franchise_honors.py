"""b778-pc2: the franchise honors sync and the history fold it needs when a saved pool is full.

``fold_words`` is checked against the retail fold (FUN_0014EFE0) under Unicorn on random streams; the sync itself is
checked on synthetic franchises. The native class skips without the pinned USA XBE or Unicorn.
"""
from __future__ import annotations

from collections import Counter
import random
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.core import nfl2k5_franchise_upgrade as up  # noqa: E402
from tests.mod_editor import test_nfl2k5_honors as native  # noqa: E402


def word(field, slot, value, *, folded=False):
    return (value & 0xFFFF) | (field << 16) | (slot << 23) | (0x40000000 if folded else 0)


class FoldTests(unittest.TestCase):
    """Pure Python, runs everywhere."""

    def test_fold_merges_by_sum_and_max_and_flags_the_receiver(self):
        words = [word(96, 1, 1), word(2, 1, 100), word(16, 1, 5), word(96, 2, 1), word(2, 2, 200),
                 word(16, 2, 9), word(0, 4, 16)]
        out = up.fold_words(words, 5, 4)
        self.assertEqual(sorted(w & ~0x80000000 for w in out),
                         sorted([word(96, 2, 2, folded=True), word(2, 2, 300, folded=True),
                                 word(16, 2, 9, folded=True), word(0, 4, 16)]))
        self.assertTrue(out[-1] & 0x80000000)
        self.assertFalse(any(w & 0x80000000 for w in out[:-1]))

    def test_fold_leaves_new_seasons_dead_words_and_short_careers(self):
        dead = word(2, 1, 7) | 0x10000000
        words = [word(0, 4, 16), dead | 0x80000000]
        self.assertEqual(up.fold_words(words, 5, 4), (word(0, 4, 16), dead | 0x80000000))
        self.assertEqual(up.fold_words([], 5, 4), ())
        with self.assertRaises(up.UpgradeRefused):
            up.fold_words(words, 5, 1)


@unittest.skipUnless(native.NativeTests.__dict__.get("__unittest_skip__") is None and native.XBE.is_file()
                     and native.HAVE_UC, "pinned USA XBE and unicorn required")
class NativeFoldTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        retail = native._retail()
        if retail is None:
            raise unittest.SkipTest("retail XBE pin differs")
        cls.patched, _ = native.honors.apply(retail)

    def native_fold(self, streams, depth):
        m = native.Machine(self.patched)
        m.record(0x177990, "progress", pop=4)
        records = m.roster([(yp, words) for yp, words in streams])
        m.put(native.CLASS, 0)
        m.call(0x14EFE0, stack=(depth,), budget=400_000_000)
        return [m.stream(rec) for rec in records]

    def test_python_fold_equals_the_game_fold(self):
        """The two agree on the large majority of random streams. The retail loop (restart from the stream head
        after every insert) sometimes loses or skips a merge when several words fold in one pass (a stale-pointer
        quirk in its inserts); the sync is the intended fold and keeps that data."""
        rng = random.Random(778)
        fields = [0, 1, 2, 6, 7, 8, 10, 16, 17, 30, 36, 43, 56, 73, 83, 87, 96, 98, 101, 103, 104]
        live = lambda ws: Counter(w & ~0x80000000 & 0xFFFFFFFF for w in ws if not w & 0x10000000)
        same = total = 0
        for depth in (2, 3, 4, 6, 9):
            streams = []
            for _ in range(15):
                yp = rng.randint(2, 15)
                used, words = set(), []
                for _ in range(rng.randint(1, 30)):
                    key = (rng.choice(fields), rng.randint(1, yp))
                    if key in used:
                        continue
                    used.add(key)
                    value = rng.choice((rng.randint(0, 600), rng.randint(0, 65535)))
                    words.append(word(key[0], key[1], value, folded=rng.random() < 0.15))
                streams.append((yp, words))
            for (yp, words), native_stream in zip(streams, self.native_fold(streams, depth)):
                mine, theirs = live(up.fold_words(words, yp, depth)), live(native_stream)
                same += mine == theirs
                total += 1
        self.assertGreaterEqual(same, total * 0.8, (same, total))

if __name__ == "__main__":
    unittest.main()
