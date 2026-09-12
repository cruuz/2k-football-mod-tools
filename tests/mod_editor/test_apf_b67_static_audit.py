"""Static receipt regeneration without distributing executable bytes."""
import json
import os
from pathlib import Path
import unittest
import tempfile

from tools.apf_b67_static_audit import audit


class StaticAuditTests(unittest.TestCase):
    def test_both_pinned_images_and_caller_boundary(self):
        try:
            import capstone  # noqa: F401
        except ImportError as exc:
            self.skipTest(f'Optional disassembler absent: {exc}')
        paths = [Path(os.environ.get(var, str(Path(tempfile.gettempdir()) / 'astra-coverage-17votk5s' / default))) for var, default in
                 (('APF_RETAIL_PE', 'base_reextracted.pe'), ('APF_RETAIL_TU_PE', 'verified_tu.pe'))]
        for path in paths:
            if not path.is_file():
                self.skipTest(f'Owned pinned image absent: {path}; set APF_RETAIL_PE and APF_RETAIL_TU_PE')
        receipt = json.loads((Path(__file__).resolve().parents[2] / 'docs/research/apf_b67_static_audit.json').read_text())
        actual = [audit(path.read_bytes()) for path in paths]
        self.assertEqual(actual, receipt['images'])
        self.assertEqual(actual[0]['direct_branches_all_aligned_words'], ['84A0504C', '84A0505C'])
        self.assertEqual(actual[1]['direct_branches_all_aligned_words'], ['84A05F04', '84A05F14'])
        self.assertTrue(all('UNCLASSIFIED' in row['classification'] for row in actual))


if __name__ == '__main__':
    unittest.main(verbosity=2)
