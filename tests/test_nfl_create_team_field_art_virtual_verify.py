from __future__ import annotations

import hashlib
import os
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import nfl_create_team_field_art_xiso_verify as verify  # noqa: E402


class CreateTeamFieldArtVirtualVerifyTests(unittest.TestCase):
    def test_virtual_full_image_hash_and_ledger(self) -> None:
        source = bytes(range(96))
        replacements = {0: 255, 47: 111, 95: 7}
        expected = bytearray(source)
        for offset, value in replacements.items():
            expected[offset] = value
        with tempfile.TemporaryDirectory(prefix="nfl-field-art-virtual-") as temp:
            path = Path(temp) / "source.bin"
            path.write_bytes(source)
            fd = os.open(path, os.O_RDONLY)
            original_size = verify.common.EXPECTED_XISO_SIZE
            try:
                verify.common.EXPECTED_XISO_SIZE = len(source)
                source_sha, output_sha, changed = verify.scan_virtual_output(
                    fd, replacements, set(replacements)
                )
            finally:
                verify.common.EXPECTED_XISO_SIZE = original_size
                os.close(fd)
        self.assertEqual(source_sha, hashlib.sha256(source).hexdigest())
        self.assertEqual(output_sha, hashlib.sha256(expected).hexdigest())
        self.assertEqual(changed, sorted(replacements))

    def test_virtual_output_refuses_ledger_and_noop_tampering(self) -> None:
        with tempfile.TemporaryDirectory(prefix="nfl-field-art-virtual-") as temp:
            path = Path(temp) / "source.bin"
            path.write_bytes(b"abcdef")
            fd = os.open(path, os.O_RDONLY)
            original_size = verify.common.EXPECTED_XISO_SIZE
            try:
                verify.common.EXPECTED_XISO_SIZE = 6
                with self.assertRaisesRegex(verify.VerifyError, "ledger"):
                    verify.scan_virtual_output(fd, {1: ord("Z")}, {2})
                with self.assertRaisesRegex(verify.VerifyError, "no-op"):
                    verify.scan_virtual_output(fd, {1: ord("b")}, {1})
            finally:
                verify.common.EXPECTED_XISO_SIZE = original_size
                os.close(fd)


if __name__ == "__main__":
    unittest.main()
