"""Execute the cache fill and field shoe selector; no manually populated cache."""
import os
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/'tools'), str(Path(__file__).parent)]
import test_nfl2k5_equipment_texture_native as native
from nfl_outer import parse_archive, read_entry_bytes
from nfl_txtr import parse_chunks
from mod_editor.core import nfl2k5_uniform_equipment_writer as writer

INDEX = Path(os.environ.get('NFL2K5_RETAIL_INDEX',
    '/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/vc_53450030/0'))


@unittest.skipUnless(native.Uc is not None and native.XBE.is_file() and INDEX.is_file(),
                     'Private retail default.xbe, pack index or Unicorn is absent')
class FieldShoeTests(unittest.TestCase):
    put = native.NativeEquipmentTests.put
    words = native.NativeEquipmentTests.words
    run_native = native.NativeEquipmentTests.run_native
    setUp = native.NativeEquipmentTests.setUp

    @classmethod
    def setUpClass(cls):
        native.NativeEquipmentTests.setUpClass()
        cls.retail = native.NativeEquipmentTests.retail
        cls.by_id, cls.groups = writer.load_targets()
        cls.archive = parse_archive(INDEX)
        # data/nfl2k5_team_names_2026.json pins Bears asset code 05.
        cls.bears = next(t for t in cls.by_id.values() if t.set_selector == '05H0' and t.name == 'shoes10')
        cls.package = read_entry_bytes(cls.archive, cls.archive.entries[cls.bears.outer_index])
        cls.chunk = parse_chunks(cls.package, allow_trailing=True)[9]
        cls.names = {t.name for t in cls.groups[cls.bears.outer_index, 9]}

    def string(self, address):
        data = bytearray()
        for offset in range(0, 256, 2):
            pair = bytes(self.uc.mem_read(address+offset, 2))
            if pair == b'\0\0': return data.decode('utf-16le')
            data.extend(pair)
        self.fail('unbounded native name')

    def test_bears_style6_clean_mud_both_feet_and_both_load_orders(self):
        from unicorn.x86_const import UC_X86_REG_EBP, UC_X86_REG_EDI
        EAX, ECX, EDX, ESP, EIP = (native.UC_X86_REG_EAX, native.UC_X86_REG_ECX,
            native.UC_X86_REG_EDX, native.UC_X86_REG_ESP, native.UC_X86_REG_EIP)
        home, away, global_context = 0x2001000, 0x2001100, 0x2001200
        descriptors = {}
        for context in (home, away, global_context):
            for name in sorted(self.names | {'bump_shoes7'}):
                number = len(descriptors)
                record, descriptor = 0x2200000+number*32, 0x2210000+number*128
                self.put(record+0x14, descriptor)
                descriptors[context, name] = (record, descriptor)
        for n, (context, name) in enumerate(((home,'HOME'),(away,'AWAY'),(global_context,'GLOBAL'))):
            at = 0x2002000+n*32
            self.uc.mem_write(at, (name+'\0').encode('utf-16le'))
            self.put(context+8, at)
        lookups = []
        missing_home_clean = [False]
        def external(uc, address, _size, _data):
            esp = uc.reg_read(ESP)
            if address == 0x4a410:
                # Only formatting and the resource hash table are doubles.
                # Cache fill, HOME/AWAY lookup, list walk and field binder run.
                fmt, values = self.words(esp+4, 2)
                fmt = self.string(fmt)
                text = (self.string(self.words(values)[0])+self.string(self.words(values+4)[0])
                        if fmt == '%s%s' else 'mask%02d' % self.words(values)[0])
                uc.mem_write(uc.reg_read(ECX), (text+'\0').encode('utf-16le'))
                pop = 12; value = len(text)
            elif address == 0x443d0:
                context, name = uc.reg_read(EAX), self.string(uc.reg_read(ECX))
                lookups.append((context, name))
                value = descriptors.get((context,name),(0,0))[0]
                if name == 'bump_shoes7' and context != global_context: value = 0
                if missing_home_clean[0] and context == home and name == 'shoes10': value = 0
                pop = 8
            else:
                return
            uc.reg_write(EAX,value); uc.reg_write(EIP,self.words(esp)[0]); uc.reg_write(ESP,esp+pop)
        self.uc.hook_add(native.UC_HOOK_CODE, external)
        self.put(0xBA2F18, 1)
        self.put(0xBA2F24, 0x2220000)
        obj, materials = 0x2004000, 0x2005000
        self.put(obj+0x1c, 2, materials)
        self.uc.mem_write(0xB6531C, bytes((1,)))
        self.uc.mem_write(0xB6531C+0x3b, bytes((0,)))
        for order in ((away,home,global_context),(home,away,global_context)):
            for n,context in enumerate(order): self.put(context, order[n+1] if n+1<len(order) else 0)
            self.put(0xB09578, order[0])
            lookups.clear()
            self.run_native(0x8e620,args=(0,0),count=150000)
            self.assertIn((home,'shoes10'),lookups)
            self.assertIn((away,'shoes10_mud'),lookups)
            for team in (0,1):
                for mud in (0,1):
                    name = 'shoes10_mud' if mud else 'shoes10'
                    context = home if team==0 else away
                    expected = descriptors[context,name][1]
                    self.assertEqual(self.words(0xB65428+(mud*192+team*96+89)*4)[0], expected)
                    frame, record = 0x300F000, 0x2008000
                    self.put(frame,0,self.stop,0,0,mud)
                    self.uc.mem_write(record+0xc,bytes((5 | (5<<3),)))
                    for register,value in ((UC_X86_REG_EBP,frame),(ESP,frame-0x24),
                        (native.UC_X86_REG_EBX,record),(native.UC_X86_REG_ESI,team),
                        (UC_X86_REG_EDI,obj),(EAX,0)):
                        self.uc.reg_write(register,value)
                    self.uc.emu_start(0x8f752,self.stop,timeout=1000000,count=20000)
                    self.assertEqual(self.uc.reg_read(EIP),self.stop)
                    self.assertEqual(self.words(materials+0x30)[0],expected)
                    self.assertEqual(self.words(materials+128+0x30)[0],expected)
            print('Native Style 6: order', ['HOME' if x==home else 'AWAY' if x==away else 'GLOBAL' for x in order],
                  'clean and mud bind each package; both feet exact; Bears',self.bears.asset_id)
        # A missing local name really does fall back to the newest context.
        missing_home_clean[0] = True
        self.put(home,away); self.put(away,global_context); self.put(global_context,0)
        self.put(0xB09578,home)
        self.run_native(0x8e620,args=(0,0),count=150000)
        self.assertEqual(self.words(0xB65428+89*4)[0],descriptors[away,'shoes10'][1])


if __name__ == '__main__': unittest.main()
