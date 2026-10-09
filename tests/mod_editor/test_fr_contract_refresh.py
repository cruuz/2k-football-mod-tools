"""New dated contract snapshots must verify before Parquet decoding."""

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import hashlib
import tempfile
import unittest
from tools.franchise_economy.import_contracts import read_pinned_parquet

class SnapshotTests(unittest.TestCase):
    def test_foreign_hash_and_undated_input_refuse_before_decoding(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'contracts.parquet';p.write_bytes(b'not parquet')
            h=hashlib.sha256(p.read_bytes()).hexdigest()
            for pin in (dict(sha256='0'*64,updated_at='2026-09-29',url='synthetic:test'),dict(sha256=h,url='synthetic:test')):
                with self.assertRaises(ValueError):read_pinned_parquet(p,pin,active_only=True)


class MinimumTests(unittest.TestCase):
    def test_six_floors_are_smallest_representable_one_year_charges(self):
        from tools.franchise_economy.contracts import fit_minimum,charges
        for minimum,expected in [(885000,920000),(1005000,1040000),(1075000,1080000),
                                 (1145000,1160000),(1215000,1240000),(1300000,1320000)]:
            fit=fit_minimum(minimum)
            self.assertEqual(fit['represented_cap_dollars'],[expected])
            f=fit['fields']
            for curve in range(8):
                for bonus in range(8):
                    below=dict(f,contract_value=f['contract_value']-1,contract_type=curve,contract_bonus=bonus)
                    self.assertLess(charges(below)[0]*4000,minimum)
            self.assertEqual(charges(f)[0]*4000,expected)

    def test_invalid_floor_or_unrepresentable_value_refuses(self):
        from tools.franchise_economy.contracts import fit_minimum
        for value in [0,-1,885000.5,True,10**12]:
            with self.assertRaises(ValueError):fit_minimum(value)


if __name__ == "__main__":
    unittest.main()
