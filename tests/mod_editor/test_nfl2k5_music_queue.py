"""Distinguish the native NOW PLAYING list from the automatic shuffle bag."""
from pathlib import Path
import struct
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests.mod_editor import test_nfl2k5_music_metadata as metadata_tests
from tests.mod_editor import test_nfl2k5_music_playlist as playlist_tests
from mod_editor.core import nfl2k5_music_metadata as metadata, nfl2k5_music_playlist as playlist
from mod_editor.core.nfl2k5_cave_oracle import XbeImage

try:
    from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
    from unicorn.x86_const import UC_X86_REG_EIP, UC_X86_REG_EAX, UC_X86_REG_ESP, UC_X86_REG_ECX, UC_X86_REG_EDX
except ImportError:
    Uc = None


class ManifestTests(unittest.TestCase):
    def test_duplicate_record_rejected_but_identical_titles_are_not_identity(self):
        with self.assertRaisesRegex(ValueError, 'Duplicate playlist'):
            playlist.Selection((('cribmusic', 59), ('cribmusic', 59)))
        # Distinct source indices can intentionally contain the same recording.
        self.assertEqual(len(playlist.Selection((('cribmusic',59),('cribmusic',60))).records),2)
        records = metadata_tests.records(80)
        for record in records: record['title'] = 'Same display title'
        self.assertEqual(len(set(metadata.identities(len(records)))),80)


@unittest.skipUnless(metadata_tests.XBE.is_file() and Uc is not None,
                     'USA retail default.xbe or Unicorn absent; native queue needs both')
class QueueTests(unittest.TestCase):
    def test_native_manual_append_allows_five_repeats_in_retail_and_custom_collection(self):
        retail = metadata_tests.XBE.read_bytes()
        patched = metadata.apply(retail, metadata_tests.records(80))[0]
        for payload, collection in ((retail,0),(patched,18)):
            with self.subTest(collection=collection):
                m = Uc(UC_ARCH_X86, UC_MODE_32)
                m.mem_map(0x10000,0x1600000)
                m.mem_map(0x2000000,0x20000)
                image = XbeImage(payload)
                for section in image.sections:
                    m.mem_write(section.start,payload[section.raw:section.raw+section.raw_size])
                stack, sentinel = 0x200F000,0x2010000
                def read(at): return struct.unpack('<I',m.mem_read(at,4))[0]
                def put(at,*values): m.mem_write(at,struct.pack('<'+'I'*len(values),*values))
                def hook(machine,address,size,user):
                    if address == 0x191D20:  # sole stub: choose synthetic profile 0
                        sp = machine.reg_read(UC_X86_REG_ESP)
                        machine.reg_write(UC_X86_REG_EAX,0)
                        machine.reg_write(UC_X86_REG_EIP,read(sp))
                        machine.reg_write(UC_X86_REG_ESP,sp+4)
                m.hook_add(UC_HOOK_CODE,hook)
                def call(va,ecx=0,edx=0,args=()):
                    put(stack,sentinel,*args)
                    for reg,v in ((UC_X86_REG_ESP,stack),(UC_X86_REG_ECX,ecx),(UC_X86_REG_EDX,edx)):
                        m.reg_write(reg,v)
                    m.emu_start(va,sentinel,count=100000)
                    self.assertEqual(m.reg_read(UC_X86_REG_EIP),sentinel,hex(va))
                    self.assertEqual(m.reg_read(UC_X86_REG_ESP),stack+4+4*len(args))
                    return m.reg_read(UC_X86_REG_EAX)
                # Execute the full native pool loop, stop before sound-device setup.
                m.reg_write(UC_X86_REG_ESP,stack)
                m.emu_start(0x27F1B0,0x27F33E,count=100000)
                self.assertEqual(m.reg_read(UC_X86_REG_EIP),0x27F33E)
                identity = call(0x27F550,collection,0)
                nodes = [call(0x27F5F0,collection,0,(identity,)) for _ in range(5)]
                self.assertEqual(len(set(nodes)),5)
                self.assertEqual(read(0xC3CC04),5)
                titles=[]
                for i,node in enumerate(nodes):
                    self.assertEqual(call(0x27F900,i),node)
                    self.assertEqual((read(node),read(node+4),read(node+8)),(collection,0,identity))
                    titles.append(call(0x27F9A0,node))
                self.assertEqual(len(set(titles)),1)
                # Profile persistence preserves repeats; rebuilding does not
                # multiply them. No save file or sound output is opened.
                call(0x27F3A0)
                saved = bytes(m.mem_read(0xBC7E50,40))
                self.assertEqual(saved, saved[:8]*5)
                for _ in range(2):
                    call(0x280530)
                    self.assertEqual(read(0xC3CC04),5)
                print(f'collection={collection}: 5 explicit appends -> 5 distinct pool nodes, same title; 2 rebuilds -> 5 nodes')

    def test_background_playlist_guards_repeated_enqueue_and_completion(self):
        patched = playlist.apply(metadata_tests.XBE.read_bytes())[0]
        vm = playlist_tests.Machine(patched,playlist.Selection(playlist.CORE[:5]))
        for _ in range(5): vm.run('enqueue')
        self.assertEqual(len(vm.queued),1)
        for _ in range(4):
            vm.complete(); vm.complete()
            vm.run('frame'); vm.run('frame')
        self.assertEqual(len(vm.queued),5)
        self.assertEqual(len(set(q[0] for q in vm.queued)),5)


if __name__ == '__main__':
    unittest.main()
