"""Execute retail screen wrappers -> patched era handlers -> kit letters.

No game loop, input device or renderer runs. Only era-number lookup and name
formatting at the final loader stage are stubbed, as in the existing harness.
"""
from pathlib import Path
import struct
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests.mod_editor import test_nfl2k5_uniform_choice as base
from mod_editor.core import nfl2k5_uniform_choice as patch

if base.Uc is not None:
    from unicorn.x86_const import UC_X86_REG_ESP, UC_X86_REG_EIP


@unittest.skipUnless(base.XBE.is_file() and base.Uc is not None,
                     'USA retail default.xbe or Unicorn absent; screen execution requires both')
class ScreenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image = patch.apply(base.XBE.read_bytes(), 'choice')[0]

    def call(self, m, va, arguments=()):
        m.mem_write(base.STACK, struct.pack('<'+'I'*(1+len(arguments)), base.SENTINEL, *arguments))
        m.reg_write(UC_X86_REG_ESP, base.STACK)
        m.emu_start(va, base.SENTINEL, count=10000)
        self.assertEqual(m.reg_read(UC_X86_REG_EIP), base.SENTINEL)
        self.assertEqual(m.reg_read(UC_X86_REG_ESP), base.STACK+4*(1+len(arguments)))

    def prepare(self):
        m = base._machine(self.image)
        # Execute the actual setup prefix and its reset call, stopping before
        # unrelated setup work; the two bulk clears and reset are not stubbed.
        for va in (patch.HOME_FLIP_VA, patch.AWAY_FLIP_VA, patch.HOME_SLOT_VA, patch.AWAY_SLOT_VA):
            m.mem_write(va, struct.pack('<I', 7))
        m.reg_write(UC_X86_REG_ESP, base.STACK)
        m.emu_start(0x77D20, 0x77D40, count=10000)
        self.assertEqual(m.reg_read(UC_X86_REG_EIP), 0x77D40)
        for va in (patch.HOME_FLIP_VA, patch.AWAY_FLIP_VA, patch.HOME_SLOT_VA, patch.AWAY_SLOT_VA):
            self.assertEqual(base._dword(m, va), 0)
        for va in (patch.HOME_TEAM_PTR_VA, patch.AWAY_TEAM_PTR_VA):
            m.mem_write(va, struct.pack('<I', base.TEAM))
        # Sparse throwbacks make skipping unavailable eras observable.
        for era in (1, 5, 14):
            m.mem_write(base.TEAM+patch.TEAM_YEARS_OFF+4*(era-1), struct.pack('<HH', 1990, 1991))
        return m

    def letters(self, m, home='NYG', away='PHI'):
        m.mem_write(base.FN_ERA_NUMBER, b'\x31\xc0\xc3')
        m.mem_write(base.FN_FORMAT, b'\x31\xc0\xc2\x08\x00')
        for ptr, addr, name in ((patch.HOME_ABBR_PTR_VA, base.STR_HOME, home),
                                (patch.AWAY_ABBR_PTR_VA, base.STR_AWAY, away)):
            m.mem_write(ptr, struct.pack('<I', addr))
            m.mem_write(addr, name.encode('utf-16le')+b'\0\0')
        # Do NOT reseed flips here: these must be the screen handlers' writes.
        m.reg_write(UC_X86_REG_ESP, base.STACK)
        m.emu_start(patch.RULE_BLOCK_VA, patch.AWAY_LETTER_CALL_VA, count=10000)
        self.assertEqual(m.reg_read(UC_X86_REG_EIP), patch.AWAY_LETTER_CALL_VA)
        sp = m.reg_read(UC_X86_REG_ESP)
        away_letter = chr(struct.unpack('<H', m.mem_read(sp+16, 2))[0])
        m.emu_start(patch.AWAY_LETTER_CALL_VA, patch.HOME_LETTER_CALL_VA, count=10000)
        self.assertEqual(m.reg_read(UC_X86_REG_EIP), patch.HOME_LETTER_CALL_VA)
        sp = m.reg_read(UC_X86_REG_ESP)
        return chr(struct.unpack('<H', m.mem_read(sp+16, 2))[0]), away_letter

    def test_both_screens_both_directions_and_sides_reach_loader_without_reseeding(self):
        for screen in (0x27AF50, 0x2C0BA0):
            for direction in ('next', 'prev'):
                for side in ('home', 'away'):
                    with self.subTest(screen=hex(screen), direction=direction, side=side):
                        m = self.prepare()
                        slot = patch.HOME_SLOT_VA if side == 'home' else patch.AWAY_SLOT_VA
                        flip = patch.HOME_FLIP_VA if side == 'home' else patch.AWAY_FLIP_VA
                        other = patch.AWAY_FLIP_VA if side == 'home' else patch.HOME_FLIP_VA
                        handler = screen + (0x20 if side == 'away' else 0) + (0x40 if direction == 'prev' else 0)
                        expected = (1, 5, 14, 0) if direction == 'next' else (14,)
                        for era in expected:
                            self.call(m, handler, (0,))
                            self.assertEqual(base._dword(m, slot), era)
                        self.assertEqual(base._dword(m, flip), 7)
                        self.assertEqual(base._dword(m, other), 0)
                        self.assertEqual(self.letters(m), ('a', 'a') if side == 'home' else ('h', 'h'))
                        self.assertEqual(base._dword(m, flip), 7)
                        # The requested survival premise is false if reset is
                        # explicitly called AFTER selection. Record it, don't
                        # alter startup lifetime without a proved bad call order.
                        self.call(m, patch.RESET_VA)
                        self.assertEqual(base._dword(m, flip), 0)
                        self.assertEqual(self.letters(m), ('h', 'a'))

    def test_both_sides_flip_independently_and_cowboys_defaults_remain(self):
        for screen in (0x27AF50, 0x2C0BA0):
            m = self.prepare()
            self.call(m, screen+0x40, (0,))
            self.call(m, screen+0x60, (0,))
            self.assertEqual(self.letters(m), ('a', 'h'))
            self.assertEqual(self.letters(m, 'DAL'), ('h', 'a'))


if __name__ == '__main__':
    unittest.main()
