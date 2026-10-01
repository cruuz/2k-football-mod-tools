"""Era views accept the same buffer inputs as their owner recognizers."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_era_rules as era


class BufferTests(unittest.TestCase):
    def test_mutable_non_era_input_is_snapshotted_without_mutation(self):
        payload = bytearray(b"not an era-owned executable")
        before = bytes(payload)
        self.assertEqual(era.underlying_view(payload), before)
        self.assertEqual(payload, before)
        payload[0] = ord("N")
        self.assertEqual(era.underlying_view(payload), bytes(payload))
        self.assertEqual(era.underlying_view(before), before)

    def test_memoryview_uses_the_current_buffer_contents(self):
        payload = bytearray(b"short foreign XBE")
        with memoryview(payload) as view:
            self.assertEqual(era.underlying_view(view), bytes(payload))
            payload[-1] = 0
            self.assertEqual(era.underlying_view(view), bytes(payload))


if __name__ == "__main__":
    unittest.main()
