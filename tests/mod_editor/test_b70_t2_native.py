"""Trace the field cache's mud argument back to its runtime record bit."""
from pathlib import Path
import struct
import sys
import unittest
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/'tools'), str(Path(__file__).parent)]
import test_nfl2k5_equipment_texture_native as n


@unittest.skipUnless(n.Uc and n.XBE.is_file(), 'Private retail executable and Unicorn are required')
class SlotFlagTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        n.NativeEquipmentTests.setUpClass()
        cls.retail = n.NativeEquipmentTests.retail
    setUp = n.NativeEquipmentTests.setUp
    put = n.NativeEquipmentTests.put
    words = n.NativeEquipmentTests.words

    def test_runtime_record_bit_selects_mud_under_dry_and_wet_weather(self):
        from unicorn import x86_const as x
        obj, record, frame = 0x2001000, 0x2002000, 0x3010000
        self.put(obj,record)
        for temperature, precipitation in ((70.,0.),(70.,.5),(20.,.5)):
            self.uc.mem_write(0xE5FFA4,struct.pack('<f',temperature))
            self.uc.mem_write(0xE5FFAC,struct.pack('<f',precipitation))
            for flag in (0,1):
                self.put(record+0x18,0x83abcdef | (flag<<28))
                self.uc.reg_write(x.UC_X86_REG_ESI,obj)
                self.uc.reg_write(x.UC_X86_REG_EBP,frame)
                self.uc.emu_start(0x8f89e,0x8f8ac,timeout=1000000,count=16)
                self.assertEqual(self.uc.reg_read(x.UC_X86_REG_EIP),0x8f8ac)
                self.assertEqual(self.words(frame-0x18)[0],flag)
                # Execute the caller's argument transport, stopping at its call.
                self.uc.reg_write(x.UC_X86_REG_EDI,0x2004000)
                self.uc.reg_write(x.UC_X86_REG_ESP,frame-64)
                self.uc.emu_start(0x8f901,0x8f90f,timeout=1000000,count=16)
                self.assertEqual(self.uc.reg_read(x.UC_X86_REG_EIP),0x8f90f)
                self.assertEqual(self.words(frame-64-4)[0],flag)
                print(f'Weather temp={temperature}, precipitation={precipitation}: record +0x18 bit28={flag} -> field mud argument={flag}')
        # J1's independently executed cache fill/field binder tests both values.
        # This bit's gameplay lifecycle is unproved; weather is not the selector here.


if __name__ == '__main__':
    unittest.main()
