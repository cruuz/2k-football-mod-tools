"""Native repair rejects foreign bytes and preserves exact byte ownership."""
import hashlib
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.b77 import vt1_repair as repair


class FixedSpans(unittest.TestCase):
    def test_hard_link_to_source_is_refused_before_any_write(self):
        with tempfile.TemporaryDirectory() as folder:
            base, output = (Path(folder) / name for name in ("base", "out"))
            base.write_bytes(b"untouched")
            os.link(base, output)
            with self.assertRaisesRegex(ValueError, "hard link"):
                repair.repair(base, output, Path(folder) / "receipts")
            self.assertEqual(base.read_bytes(), b"untouched")

    def test_streamed_hash_and_full_compare_cross_chunk_boundary(self):
        with tempfile.TemporaryDirectory() as folder:
            base, output = (Path(folder) / name for name in ("base", "out"))
            source = bytes((i % 251 for i in range((1 << 20) + 32)))
            edits = [(3, source[3:7], b"ABCD", "first"),
                     ((1 << 20) - 2, source[(1 << 20) - 2:(1 << 20) + 3], b"12345", "boundary")]
            final = bytearray(source)
            for offset, before, after, _ in edits:
                final[offset:offset + len(before)] = after
            base.write_bytes(source)
            output.write_bytes(final)
            self.assertEqual(repair.patched_digest(base, edits), hashlib.sha256(final).hexdigest())
            receipt = repair.compare(base, output, edits)
            self.assertEqual(receipt["bytes_compared"], len(source))
            self.assertEqual(receipt["changed_bytes"], 9)
            self.assertEqual(receipt["outside_spans_changed_bytes"], 0)
            final[20] ^= 1
            output.write_bytes(final)
            with self.assertRaisesRegex(ValueError, "Unexpected bytes"):
                repair.compare(base, output, edits)

    def test_wrong_source_span_refuses(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "base"
            path.write_bytes(b"abcdef")
            with self.assertRaisesRegex(ValueError, "Source span changed"):
                repair.patched_digest(path, [(1, b"wrong", b"fixed", "foreign")])

    def test_unknown_disc_refuses_before_creating_output(self):
        with tempfile.TemporaryDirectory() as folder:
            base, output = (Path(folder) / name for name in ("base", "out"))
            base.write_bytes(b"unknown")
            with self.assertRaisesRegex(ValueError, "Unexpected base image size"):
                repair.repair(base, output, Path(folder) / "receipts")
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
