"""Reproduce sparse receipt from private pinned input, never retail fixtures."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.apf_b69_playcalling_audit import audit


class AuditTests(unittest.TestCase):
    def test_sparse_receipt_matches_pinned_private_image(self):
        image = Path(os.environ.get('APF_RETAIL_PE', str(Path(tempfile.gettempdir()) /
            'astra-coverage-17votk5s/base_reextracted.pe')))
        if not image.is_file():
            self.skipTest('Owned pinned BASE PE absent; set APF_RETAIL_PE')
        receipt = Path(__file__).resolve().parents[2] / 'docs/research/apf_b69_control_audit.json'
        self.assertEqual(audit(image.read_bytes()), json.loads(receipt.read_text()))


if __name__ == '__main__':
    unittest.main(verbosity=2)
