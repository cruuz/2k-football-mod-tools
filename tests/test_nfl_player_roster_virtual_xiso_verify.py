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

import nfl_player_roster_xiso_verify as verify  # noqa: E402


class PlayerRosterVirtualOutputTests(unittest.TestCase):
    def test_virtual_scan_hashes_overlay_without_publishing_output(self) -> None:
        source = bytes(range(64))
        replacements = {5: 205, 31: 131, 63: 99}
        expected = bytearray(source)
        for offset, value in replacements.items():
            expected[offset] = value
        with tempfile.TemporaryDirectory(prefix="nfl-roster-virtual-") as temp:
            path = Path(temp) / "source.bin"
            path.write_bytes(source)
            fd = os.open(path, os.O_RDONLY)
            original_size = verify.IMAGE_SIZE
            try:
                verify.IMAGE_SIZE = len(source)
                source_sha, output_sha, changed = verify.scan_virtual_output(
                    fd, replacements, set(replacements)
                )
                read = verify.virtual_reader(fd, replacements)
                self.assertEqual(read(0, len(source)), bytes(expected))
                self.assertEqual(read(29, 5), bytes(expected[29:34]))
            finally:
                verify.IMAGE_SIZE = original_size
                os.close(fd)
        self.assertEqual(source_sha, hashlib.sha256(source).hexdigest())
        self.assertEqual(output_sha, hashlib.sha256(expected).hexdigest())
        self.assertEqual(changed, sorted(replacements))

    def test_virtual_scan_refuses_ledger_or_noop_tampering(self) -> None:
        with tempfile.TemporaryDirectory(prefix="nfl-roster-virtual-") as temp:
            path = Path(temp) / "source.bin"
            path.write_bytes(b"abcdef")
            fd = os.open(path, os.O_RDONLY)
            original_size = verify.IMAGE_SIZE
            try:
                verify.IMAGE_SIZE = 6
                with self.assertRaisesRegex(verify.VerifyError, "ledger"):
                    verify.scan_virtual_output(fd, {1: ord("Z")}, {2})
                with self.assertRaisesRegex(verify.VerifyError, "does not change"):
                    verify.scan_virtual_output(fd, {1: ord("b")}, {1})
            finally:
                verify.IMAGE_SIZE = original_size
                os.close(fd)


if __name__ == "__main__":
    unittest.main()
