"""Portable census checks, especially Ghidra pointer writes and function attribution."""
from pathlib import Path
import hashlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.nfl2k5_roster_storage_audit import corpus_census


class AuditTests(unittest.TestCase):
    def test_pointer_writes_count_but_function_comment_constants_do_not(self):
        source = (b'/*\n * address: 0x000C1F00\n * callees: 0x1f4\n */\n'
                  b'  *(int *)(DAT_00b72918 + 0x18) = 500;\n'
                  b'  x = x + 0x1f4;\n'
                  b'/*\n * address: 0x002418C0\n */\n'
                  b'  *(int *)(p + 0x1f2) = 65;\n')
        with tempfile.TemporaryDirectory(prefix='roster-census-') as tmp:
            root = Path(tmp).resolve()
            (root / 'pseudo_c').mkdir()
            (root / 'pseudo_c/shard.c').write_bytes(source)
            result = corpus_census(root)
        self.assertEqual(result['function_count'], 2)
        self.assertEqual(result['counts']['team_stride'], {'lines':2, 'functions':1})
        self.assertEqual(result['candidates']['team_stride'], [
            ['0x000c1f00', 'shard.c', 5], ['0x000c1f00', 'shard.c', 6]])
        self.assertEqual(result['candidates']['team_reserve_metadata'], [['0x002418c0', 'shard.c', 10]])
        self.assertEqual(result['shard_sha256']['shard.c'], hashlib.sha256(source).hexdigest())

    def test_absent_corpus_is_not_an_empty_proof(self):
        with tempfile.TemporaryDirectory(prefix='missing-census-') as tmp:
            with self.assertRaisesRegex(ValueError, 'shards absent'):
                corpus_census(Path(tmp))


if __name__ == '__main__':
    unittest.main()
