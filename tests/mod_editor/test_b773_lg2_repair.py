"""Fixed-span writer safety and complete scope comparison, without copying a disc."""
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.b77 import lg2_repair as repair


class RepairTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.before = Path(self.temp.name) / 'before.bin'
        self.after = Path(self.temp.name) / 'after.bin'
        self.original = bytes(range(256)) * 20
        self.fixed = self.original[:255] + b'ABC' + self.original[258:]
        self.rows = [dict(offset=255, size=3, before=self.original[255:258].hex(), after=b'ABC'.hex())]
        self.before.write_bytes(self.original)
        self.after.write_bytes(self.original)

    def write(self, rows=None):
        return repair.write_spans(self.after, self.rows if rows is None else rows,
                                  repair.sha(self.original), repair.sha(self.fixed))

    def test_write_replay_and_physical_scope(self):
        self.assertEqual(self.write()['changed_bytes'], 3)
        self.assertEqual(self.after.read_bytes(), self.fixed)
        self.assertEqual(self.write()['write_bytes'], 0)
        proof = repair.stream_compare(self.before, self.rows, self.after)
        self.assertEqual(proof['compared_bytes'], len(self.original))
        self.assertEqual(proof['outside_scope_changed_bytes'], 0)
        self.assertTrue(proof['physical_disc_compare'])

    def test_unknown_target_and_wrong_expected_span_never_write(self):
        wrong = [dict(self.rows[0], before='000000')]
        with self.assertRaisesRegex(ValueError, 'prewrite span mismatch'):
            self.write(wrong)
        self.assertEqual(self.after.read_bytes(), self.original)
        self.after.write_bytes(b'foreign')
        with self.assertRaisesRegex(ValueError, 'unknown target hash'):
            self.write()
        self.assertEqual(self.after.read_bytes(), b'foreign')

    def test_scope_rejects_outside_change_truncation_and_extra_bytes(self):
        for bad in (b'X' + self.fixed[1:], self.fixed[:-1], self.fixed + b'X'):
            self.after.write_bytes(bad)
            with self.assertRaises(ValueError):
                repair.stream_compare(self.before, self.rows, self.after)

    def test_virtual_scope_explicitly_is_not_physical(self):
        proof = repair.stream_compare(self.before, self.rows)
        self.assertFalse(proof['physical_disc_compare'])
        self.assertEqual(proof['after_sha256'], repair.sha(self.fixed))
        self.assertEqual(self.after.read_bytes(), self.original)

    def test_symlink_and_unknown_xbe_refused(self):
        self.after.unlink()
        try:
            self.after.symlink_to(self.before)
        except OSError:
            self.skipTest('symlinks unavailable')
        with self.assertRaisesRegex(ValueError, 'symlink target'):
            self.write()
        self.assertEqual(self.before.read_bytes(), self.original)
        with self.assertRaisesRegex(ValueError, 'unknown XBE hash'):
            repair.repair_xbe(self.original)


if __name__ == '__main__':
    unittest.main()
