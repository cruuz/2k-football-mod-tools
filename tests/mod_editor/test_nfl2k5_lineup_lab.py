"""Offline validation of the gdb target decoder, with no emulator launch."""
import struct
import unittest
from sd.lab.fatigue import force_defense


class FatigueTargetTests(unittest.TestCase):
    def fixture(self, away=False):
        mem, writes = {}, []
        def put(a, b):
            mem.update({a+i: v for i, v in enumerate(b)})
        def read(a, n):
            return bytes(mem[a+i] for i in range(n))
        def u32(a, n):
            put(a, struct.pack('<I', n))
        stack, desc, roster, team = 0x1000, 0x2000, 0x3000, 0x4000
        u32(stack + 0x10, desc)
        u32(stack + 0x14, 0xE5FD00 if away else 0xE5FC20)
        put(desc + 5, bytes([12, 13, 14, 15, 14, 16, 17, 18, 18, 18, 18]))
        put(0x61C80 if away else 0x61C70, b'\xb8' + struct.pack('<I', roster) + b'\xc3')
        u32(roster, team)
        put(team + 0x11C, b'\x0b')
        for i in range(11):
            p, w, f = 0x5000 + 0x100*i, 0x7000 + 0x100*i, 0x9000 + 0x100*i
            u32(team + i*4, p)
            put(p + 0x35, bytes([10 if i == 0 else 11 if i == 1 else 16]))
            put(p + 0x34, bytes([0 if away else 1]))
            u32(p + 0x30, w)
            u32(w + 4, f)
            u32(w + 0x10, 0)
            put(f + 4, struct.pack('<f', 1.0))
        u32(0xE601A4 if away else 0xE60194, 5)
        u32(0xE601A8 if away else 0xE60198, 16)
        def write(a, b):
            writes.append((a, b))
            put(a, b)
        return read, write, put, writes, stack, desc

    def test_home_and_away_decode_only_lb_and_legacy_olb(self):
        for away in (False, True):
            read, write, put, writes, stack, _ = self.fixture(away)
            r = force_defense(read, write, stack)
            self.assertEqual([p['enum'] for p in r['linebackers']], [10, 11])
            self.assertEqual(writes, [(0x9004, bytes(4)), (0x9104, bytes(4))])
            self.assertEqual(read(0x9204, 4), struct.pack('<f', 1.0))

    def test_offense_is_ignored(self):
        read, write, put, writes, stack, desc = self.fixture()
        put(desc + 5, bytes(11))
        self.assertIsNone(force_defense(read, write, stack))
        self.assertFalse(writes)

    def test_entire_set_validated_before_any_write(self):
        read, write, put, writes, stack, _ = self.fixture()
        put(0x9104, struct.pack('<f', float('nan')))
        with self.assertRaises(ValueError):
            force_defense(read, write, stack)
        self.assertFalse(writes)


if __name__ == '__main__':
    unittest.main()
